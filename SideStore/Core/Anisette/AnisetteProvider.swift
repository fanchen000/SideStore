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


    // Renewal uses a remote Anisette profile when the old on-device identity
    // yields Apple -80045. This does not clear ADI, revoke certificates,
    // register App IDs or change the user's preference before verification.
    static func fetchForSessionRenewal(handler: AnisetteServerHandler? = nil) async throws -> ALTAnisetteData {
        if UserDefaults.standard.useOnDeviceAnisette {
            debugLog("[AnisetteProvider] renewal_source=temporary_remote")
            return try await fetchRemote(handler: handler)
        }
        return try await fetch(handler: handler)
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
                let secureServers = refreshed.filter { URL(string: $0)?.scheme == "https" }
                if !secureServers.isEmpty {
                    return try await fetchRemote(handler: handler, allowCatalogRecovery: false,
                                                 candidateServerStrings: secureServers)
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

        let effectiveServers = UserDefaults.standard.disableAnisetteRotation ? [servers[startIndex]] : servers
        let effectiveStartIndex = UserDefaults.standard.disableAnisetteRotation ? 0 : startIndex
        let fetchResult: (data: ALTAnisetteData, newAdiBlob: Data?)
        do {
            fetchResult = try await provider.fetchAnisetteDataWithFailover(
            servers: effectiveServers,
            startIndex: effectiveStartIndex,
            identifier: identifier,
            existingAdiBlob: existingBlob,
            headers: headers,
            onError: { error in
                if let anisetteError = error as? SideSign.AnisetteError {
                    switch anisetteError {
                    case .incorrectlyProvisioned:
                        debugLog("[AnisetteProvider] Possible ADI desynchronization; preserving provisioning state.")
                        return false
                    case .badServerResponse(_, let payload) where payload.contains("-45061"):
                        debugLog("[AnisetteProvider] ADI error -45061; preserving provisioning state.")
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
            // Only retry once, after a catalog refresh discovers new HTTPS
            // endpoints. Never clear the original ADI or repeat a failed host.
            if allowCatalogRecovery && !UserDefaults.standard.disableAnisetteRotation {
                await AnisetteServersManager.shared.syncOnFailureIfNeeded()
                let refreshed = await AnisetteServersManager.shared.getActiveServerURLs()
                let oldServers = Set(serverUrlStrings)
                let newServers = refreshed.filter {
                    !oldServers.contains($0) && URL(string: $0)?.scheme == "https"
                }
                if !newServers.isEmpty {
                    debugLog("[AnisetteProvider] New HTTPS catalog endpoint available; retrying once.")
                    return try await fetchRemote(handler: handler, allowCatalogRecovery: false,
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
