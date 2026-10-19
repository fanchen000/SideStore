//
//  AnisetteProvider.swift
//  SideStore
//
//  Created by Magesh K on 8/9/26.
//  Copyright © 2026 SideStore. All rights reserved.
//

import Foundation
import SideSign

enum AnisetteProvider {
    static func fetch(handler: AnisetteServerHandler? = nil) async throws -> ALTAnisetteData {
        if UserDefaults.standard.useOnDeviceAnisette {
            debugLog("[AnisetteProvider] Fetching anisette via On-Device Anisette (ODA)...")
            return try await OnDeviceAnisetteManager.shared.fetchAnisetteData()
        } else {
            debugLog("[AnisetteProvider] Fetching anisette via remote server...")
            return try await fetchRemote(handler: handler)
        }
    }

    private static func fetchRemote(
        handler: AnisetteServerHandler? = nil,
        allowCatalogRecovery: Bool = true,
        candidateServerStrings: [String]? = nil
    ) async throws -> ALTAnisetteData {
        let serverUrlStrings: [String]
        if let candidateServerStrings {
            serverUrlStrings = candidateServerStrings
        } else {
            serverUrlStrings = await AnisetteServersManager.shared.getActiveServerURLs()
        }
        let servers = serverUrlStrings.compactMap { URL(string: $0) }
        guard !servers.isEmpty else {
            if allowCatalogRecovery && !UserDefaults.standard.disableAnisetteRotation {
                await AnisetteServersManager.shared.syncOnFailureIfNeeded()
                let refreshed = await AnisetteServersManager.shared.getActiveServerURLs()
                // Catalog-driven automatic fallback must not silently send
                // existing ADI provisioning data to an insecure endpoint.
                let available = refreshed.filter {
                    guard let url = URL(string: $0) else { return false }
                    return url.scheme == "https" && url.host != nil
                }
                if !available.isEmpty {
                    return try await fetchRemote(
                        handler: handler, allowCatalogRecovery: false,
                        candidateServerStrings: available)
                }
            }
            throw AnisetteError.noServersConfigured
        }

        let lastServer = UserDefaults.standard.menuAnisetteURL
        let startIndex = servers.firstIndex(where: { $0.absoluteString == lastServer }) ?? 0

        let provider = SideSign.AnisetteDataManager.shared
        let existingBlob = AnisetteConfigManager.shared.anisetteAdiBlob.flatMap { Data(base64Encoded: $0) }
        let identifier = await AnisetteConfigManager.shared.resolveDeviceIdentifier()
        let headers = await AnisetteConfigManager.shared.makeRequestHeaders()
        // Safe, non-sensitive runtime evidence of which client profile reaches
        // SideSign. Never log the raw headers, identifiers or Apple credentials.
        let profileKind: String = {
            let clientInfo = headers.clientInfo ?? ""
            if clientInfo.contains("Pixel") || clientInfo.contains("Android") {
                return "android_custom"
            }
            if clientInfo.contains("Windows") { return "windows" }
            return "other"
        }()
        debugLog("[AnisetteProvider] effective_client_profile=\(profileKind)")

        let fetchResult: (data: ALTAnisetteData, newAdiBlob: Data?)
        do {
            fetchResult = try await provider.fetchAnisetteDataWithFailover(
            servers: UserDefaults.standard.disableAnisetteRotation ? [servers[startIndex]] : servers,
            startIndex: startIndex,
            identifier: identifier,
            existingAdiBlob: existingBlob,
            headers: headers,
            onError: { error in
                if let anisetteError = error as? SideSign.AnisetteError {
                    switch anisetteError {
                    case .incorrectlyProvisioned:
                        debugLog("[AnisetteProvider] Possible ADI desynchronization; preserved local state for explicit recovery.")
                        return false
                    case .badServerResponse(_, let payload) where payload.contains("-45061"):
                        debugLog("[AnisetteProvider] ADI error -45061; preserved local state for explicit recovery.")
                        return false
                    case .outdatedV1Server(let serverURL, _):
                        if UserDefaults.standard.defaultServerURL == serverURL.absoluteString {
                            return true
                        }
                        if let handler = handler {
                            let shouldContinue = try await handler.warnOutdatedAnisetteServer()
                            if shouldContinue {
                                UserDefaults.standard.defaultServerURL = serverURL.absoluteString
                            }
                            return shouldContinue
                        }
                    default:
                        break
                    }
                }
                return false
            },
            onSuccess: { successfulServer in
                // SideSign's authentication hsc=434 recovery calls
                // AnisetteDataManager.shared.resync(), which uses activeMode.
                // A one-off remote fetch does not set that mode itself.
                // Bind the *successful* provider only, so the resync request
                // targets the same identity/server as the initial Anisette.
                SideSign.AnisetteDataManager.shared.setMode(.remote(server: successfulServer))
                UserDefaults.standard.menuAnisetteURL = successfulServer.absoluteString
                debugLog("[AnisetteProvider] Successfully fetched Anisette data from \(successfulServer.absoluteString)")
            }
            )
        } catch {
            // Provisioning/ADI identity errors are not server outages. Trying
            // a new server with the same invalid provisioning identity could
            // propagate corrupted state and cannot repair it. Fail closed.
            if let anisetteError = error as? SideSign.AnisetteError {
                switch anisetteError {
                case .incorrectlyProvisioned:
                    throw error
                case .badServerResponse(_, let payload) where payload.contains("-45061"):
                    throw error
                default:
                    break
                }
            }
            // Do not reset ADI, change the signed-in account, or retry the same
            // failed endpoints indefinitely. Refresh the catalog once and retry
            // only if a genuinely new, user-visible active endpoint appears.
            if allowCatalogRecovery && !UserDefaults.standard.disableAnisetteRotation {
                await AnisetteServersManager.shared.syncOnFailureIfNeeded()
                let refreshed = await AnisetteServersManager.shared.getActiveServerURLs()
                let previous = Set(serverUrlStrings)
                let newServers = refreshed.filter {
                    guard !previous.contains($0), let url = URL(string: $0) else {
                        return false
                    }
                    return url.scheme == "https" && url.host != nil
                }
                if !newServers.isEmpty {
                    debugLog("[AnisetteProvider] Catalog supplied a new endpoint; retrying one time.")
                    return try await fetchRemote(
                        handler: handler, allowCatalogRecovery: false,
                        candidateServerStrings: newServers)
                }
            }
            throw error
        }

        let (anisetteData, newAdiBlob) = fetchResult

        if let freshBlob = newAdiBlob {
            AnisetteConfigManager.shared.anisetteAdiBlob = freshBlob.base64EncodedString()
        }

        return anisetteData
    }
}
