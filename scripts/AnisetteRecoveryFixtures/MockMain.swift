import Foundation
import SideSign
@main struct Tests {
 static func main() async throws {
  let urls=["https://old.example","https://new.example"]
  let adi=AnisetteConfigManager.shared.anisetteAdiBlob
  let manager=AnisetteServersManager.shared
  let signer=SideSign.AnisetteDataManager.shared
  let prefs=UserDefaults.standard
  prefs.useOnDeviceAnisette=false
  prefs.disableAnisetteRotation=false
  prefs.menuAnisetteURL=urls[0]

  // Only newly discovered endpoint is tried again after a failed catalog.
  await manager.configure(names:[urls[0]],updated:urls)
  signer.reset(); signer.successful=urls[1]
  let ok = try await AnisetteProvider.fetch()
  precondition(ok.marker=="ok")
  precondition(signer.attempts==urls, "retries must be new endpoint only")
  let countA=await manager.counts(); precondition(countA==1)
  precondition(adi==AnisetteConfigManager.shared.anisetteAdiBlob)
  print("PASS: new server adopted without clearing ADI")

  // No newly discovered endpoint: do not hammer identical failed server.
  await manager.configure(names:[urls[0]],updated:[urls[0]])
  signer.reset()
  do { _=try await AnisetteProvider.fetch(); fatalError("expected failure") } catch {}
  precondition(signer.attempts==[urls[0]])
  let countB=await manager.counts(); precondition(countB==1)
  precondition(adi==AnisetteConfigManager.shared.anisetteAdiBlob)
  print("PASS: no repeat against unchanged failing server")

  // Explicit disable rotation is respected, with no sync and no alternate.
  prefs.disableAnisetteRotation=true
  await manager.configure(names:[urls[0]],updated:urls)
  signer.reset(); signer.successful=urls[1]
  do { _=try await AnisetteProvider.fetch(); fatalError("expected failure") } catch {}
  let count0=await manager.counts(); precondition(count0==0)
  precondition(signer.attempts==[urls[0]])
  prefs.disableAnisetteRotation=false
  print("PASS: user opt-out respected")

  // Empty list can recover through catalog without an infinite loop.
  await manager.configure(names:[],updated:[urls[1]])
  signer.reset(); signer.successful=urls[1]
  _=try await AnisetteProvider.fetch()
  let countD=await manager.counts(); precondition(countD==1)
  precondition(signer.attempts==[urls[1]])
  print("PASS: empty catalog recovery")
  await manager.configure(names:[urls[0]],updated:[urls[0],"http://blocked.example"])
  signer.reset(); signer.successful="http://blocked.example"
  do { _=try await AnisetteProvider.fetch(); fatalError("insecure server should not be used") } catch {}
  precondition(signer.attempts==[urls[0]])
  precondition(adi==AnisetteConfigManager.shared.anisetteAdiBlob)
  print("PASS: non-HTTPS fallback rejected")
  // Device identity errors must not spray stored ADI to other servers.
  await manager.configure(names:[urls[0]],updated:urls)
  signer.reset(); signer.specialError = .incorrectlyProvisioned
  do { _=try await AnisetteProvider.fetch(); fatalError("must fail closed on provision error") } catch {}
  let countProvision=await manager.counts(); precondition(countProvision==0)
  precondition(signer.attempts==[urls[0]])
  precondition(adi==AnisetteConfigManager.shared.anisetteAdiBlob)
  print("PASS: provisioning error fails closed without ADI mutation")
  await manager.configure(names:[urls[0]],updated:urls)
  signer.reset(); signer.specialError = .badServerResponse(503,"-45061")
  do { _=try await AnisetteProvider.fetch(); fatalError("must fail closed on -45061") } catch {}
  let countAdi=await manager.counts(); precondition(countAdi==0)
  precondition(signer.attempts==[urls[0]])
  precondition(adi==AnisetteConfigManager.shared.anisetteAdiBlob)
  print("PASS: -45061 preserves ADI and blocks cross-server retry")
  print("ANISI_CATALOG_RECOVERY_7_OF_7_PASS")
 }
}
