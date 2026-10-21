"""Fail-closed source-level contracts for the in-place Apple session renewal UI.

Real iOS compilation is performed by the workflow's Xcode archive stage.
These checks specifically prevent a future refactor from turning account
renewal into sign-out, credential clearing, certificate revocation, or resign.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding="utf8")

class SessionRenewalSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = read("AltStore/Settings/SettingsViewController.swift")
        cls.auth = read("SideStore/Core/Auth/AuthManager.swift")
        cls.flow = read("SideStore/Core/Operations/StandaloneOperations/SignInOperation.swift")
        cls.anisette = read("SideStore/Core/Anisette/AnisetteProvider.swift")
        cls.renew = cls.ui.split("func renewAppleSession()", 1)[1].split("\n    func signIn()", 1)[0]

    def test_visible_entry_keeps_sign_out_accessible(self):
        self.assertIn('setTitle(NSLocalizedString("MANAGE"', self.ui)
        self.assertIn('title: NSLocalizedString("Renew Session"', self.ui)
        self.assertIn('title: NSLocalizedString("Sign Out"', self.ui)

    def test_reauth_does_not_sign_out_or_clear_credentials(self):
        self.assertNotIn("signOut(", self.renew)
        self.assertNotIn("clearSignInInfo", self.renew)
        self.assertNotIn("clearActiveCertificate", self.renew)

    def test_all_high_risk_flows_are_disabled(self):
        for flag in ("skipDeviceRegistration", "skipCertificateProvisioning",
                     "skipResign", "skipHowTos"):
            self.assertIn(flag + ": true", self.renew)

    def test_identity_binding(self):
        self.assertIn("expectedTeamIdentifier: existingTeamID", self.renew)
        self.assertIn("expectedAppleID: existingAppleID", self.renew)
        self.assertIn("appleID.caseInsensitiveCompare(expectedAppleID)", self.flow)
        self.assertIn("team.identifier == expectedTeamIdentifier", self.flow)

    def test_password_not_committed_before_team_check(self):
        login = self.flow.split("private func signIn(appleID:", 1)[1].split(
            "// Persistence Helpers", 1)[0]
        self.assertIn("pendingReauthenticationPassword = password", login)
        self.assertIn("if expectedTeamIdentifier != nil", login)
        flow = self.flow.split("private func startAuthentication(", 1)[1].split(
            "private func authenticationLoop()", 1)[0]
        self.assertLess(flow.index("team.identifier == expectedTeamIdentifier"),
                        flow.index("AuthManager.shared.adsid = session.dsid"))

    def test_pending_password_cleared_on_failure(self):
        self.assertIn("self.pendingReauthenticationPassword = nil", self.flow)

    def test_guard_rejects_unsafe_renewal_options(self):
        self.assertIn('Session renewal cannot alter device, certificate, or signed apps.', self.flow)
        for flag in ("!skipDeviceRegistration", "!skipCertificateProvisioning",
                     "!skipResign", "!skipHowTos"):
            self.assertIn(flag, self.flow)

    def test_auth_manager_passes_expected_identifiers(self):
        self.assertIn("expectedTeamIdentifier: expectedTeamIdentifier", self.auth)
        self.assertIn("expectedAppleID: expectedAppleID", self.auth)

    def test_new_session_validates_team_before_keychain_replacement(self):
        f = self.flow.split("private func fetchTeam(for account:", 1)[1]
        self.assertIn("if expectedTeamIdentifier != nil", f)
        self.assertIn("ALTAppleAPI.shared.fetchTeams(for: account, session: session)", f)
        self.assertIn("DeveloperPortalProxy.shared.fetchTeams(for: account)", f)

    def test_renewal_uses_remote_without_destroying_saved_identity(self):
        self.assertIn("fetchForSessionRenewal(handler: anisetteServerHandler)", self.flow)
        self.assertIn("renewalOriginalAdiBlob = AnisetteConfigManager.shared.anisetteAdiBlob", self.flow)
        self.assertIn("AnisetteConfigManager.shared.anisetteAdiBlob = renewalOriginalAdiBlob", self.flow)
        self.assertIn("UserDefaults.standard.menuAnisetteURL = renewalOriginalServerURL", self.flow)
        self.assertIn("renewal_source=temporary_remote", self.anisette)
        self.assertIn("return try await fetchRemote(handler: handler)", self.anisette)

    def test_persist_remote_mode_only_after_final_verification(self):
        fragment = self.flow.split("try await self.finalizeAuthentication(result: .success(authResult))", 1)[1]
        self.assertIn("if renewalTemporaryRemote {", fragment)
        self.assertIn("UserDefaults.standard.useOnDeviceAnisette = false", fragment)
        self.assertNotIn("signOut(", fragment.split("} catch {", 1)[0])

if __name__ == "__main__":
    unittest.main()
