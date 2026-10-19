import Foundation
public struct AnisetteData: Sendable, Equatable { public let marker: String; public init(_ marker: String){self.marker=marker} }
public struct AnisetteRequestHeaders: Sendable {public let clientInfo: String?; public init(clientInfo: String?){self.clientInfo=clientInfo}}
public enum AnisetteError: Error {
 case noServersConfigured
 case incorrectlyProvisioned
 case badServerResponse(Int, String)
 case outdatedV1Server(URL, String)
}
public enum AnisetteMode {case remote(server: URL)}
public final class AnisetteDataManager: @unchecked Sendable {
 public static let shared=AnisetteDataManager()
 public var attempts=[String]()
 public var successful: String?
 public var specialError: AnisetteError?
 public func setMode(_ mode: AnisetteMode) {}
 public func reset(){attempts=[]; successful=nil; specialError=nil}
 public func fetchAnisetteDataWithFailover(
   servers: [URL], startIndex: Int, identifier: UUID,
   existingAdiBlob: Data?, headers: AnisetteRequestHeaders,
   onError: @Sendable (Error) async throws -> Bool,
   onSuccess: @Sendable (URL) -> Void
 ) async throws -> (data: AnisetteData, newAdiBlob: Data?) {
    for server in servers {
      attempts.append(server.absoluteString)
      if let specialError { _=try await onError(specialError); throw specialError }
      if server.absoluteString==successful {onSuccess(server);return (AnisetteData("ok"),nil)}
      _=try await onError(AnisetteError.badServerResponse(503,"mock outage"))
    }
    throw AnisetteError.badServerResponse(503,"all failed")
 }
}
