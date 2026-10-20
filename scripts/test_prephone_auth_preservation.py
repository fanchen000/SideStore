"""Offline safety regression for the SideStore-in-LiveContainer auth path.

This is source-level validation. It does not claim that Apple login, signing,
refresh or an iCTRL XCTest runner can work on a disconnected device.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


class PrePhoneAuthenticationSafety(unittest.TestCase):
    def test_anisette_never_auto_destroys_provisioning(self):
        provider = source("SideStore/Core/Anisette/AnisetteProvider.swift")
        assert "anisetteAdiBlob = nil" not in provider
        assert "case .incorrectlyProvisioned:" in provider
        assert 'payload.contains("-45061")' in provider
        assert "return false" in provider

    def test_catalog_failover_is_https_and_bounded(self):
        provider = source("SideStore/Core/Anisette/AnisetteProvider.swift")
        assert "allowCatalogRecovery: Bool = true" in provider
        assert provider.count("allowCatalogRecovery: false") == 2
        assert provider.count('URL(string: $0)?.scheme == "https"') == 2
        assert "!oldServers.contains($0)" in provider
        assert "let effectiveStartIndex = UserDefaults.standard.disableAnisetteRotation ? 0 : startIndex" in provider

    def test_catalog_does_not_override_selected_server(self):
        manager = source("SideStore/Core/Anisette/AnisetteServersManager.swift")
        block = manager.split("public func loadLocalServers()", 1)[1].split("// If user-facing file", 1)[0]
        assert "if currentURL.isEmpty" in block
        assert 'currentURL.contains("ani.sidestore.io")' not in block

    def test_login_failure_does_not_clear_user_state(self):
        sign_in = source("SideStore/Core/Operations/StandaloneOperations/SignInOperation.swift")
        assert "await AuthManager.shared.signOut()" not in sign_in
        assert "anisetteAdiBlob = nil" not in sign_in
        assert "await handler.handleSignInResult(.failure(error))" in sign_in

    def test_auth_ready_matches_actual_refresh_requirements(self):
        manager = source("SideStore/Core/Auth/AuthManager.swift")
        ready = manager.split("public var isAuthenticated: Bool", 1)[1].split("public var currentAppleID", 1)[0]
        assert "hasAdsid" in ready
        assert "hasToken" in ready
        assert "hasPassword" not in ready
        assert "return hasEmail && hasAdsid && hasToken" in ready
        assert "throw OperationError.notAuthenticated" in manager


if __name__ == "__main__":
    unittest.main()
