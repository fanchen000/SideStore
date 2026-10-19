import Foundation
import SideSign
typealias ALTAnisetteData = AnisetteData
typealias AnisetteError = SideSign.AnisetteError
func debugLog(_ s:String){}
extension UserDefaults {
 var useOnDeviceAnisette:Bool { get{bool(forKey: "oda")} set{set(newValue,forKey:"oda")} }
 var disableAnisetteRotation:Bool { get{bool(forKey: "disableRotation")} set{set(newValue,forKey:"disableRotation")} }
 var menuAnisetteURL:String { get{string(forKey:"serverURL") ?? ""} set{set(newValue,forKey:"serverURL")} }
 var defaultServerURL:String? {get{string(forKey:"defaultServerURL")} set{set(newValue,forKey:"defaultServerURL")}}
}
final class AnisetteConfigManager: @unchecked Sendable {
 static let shared=AnisetteConfigManager()
 var anisetteAdiBlob:String? = Data("PRESERVED_ADI".utf8).base64EncodedString()
 func resolveDeviceIdentifier() async -> UUID { UUID() }
 func makeRequestHeaders() async -> AnisetteRequestHeaders { AnisetteRequestHeaders(clientInfo:"Windows") }
}
final class AnisetteServerHandler: @unchecked Sendable{
 func warnOutdatedAnisetteServer() async throws -> Bool {false}
}
actor OnDeviceAnisetteManager {
 static let shared=OnDeviceAnisetteManager()
 func fetchAnisetteData() async throws -> ALTAnisetteData { AnisetteData("on-device") }
}
actor AnisetteServersManager {
 static let shared=AnisetteServersManager()
 var names=["https://first.example"]
 var updated=["https://first.example"]
 var syncCalls=0
 func getActiveServerURLs()->[String]{names}
 func syncOnFailureIfNeeded() async {syncCalls+=1;names=updated}
 func configure(names:[String], updated:[String]) {self.names=names;self.updated=updated;self.syncCalls=0}
 func counts()->Int {syncCalls}
}
Process exited with code 0.
