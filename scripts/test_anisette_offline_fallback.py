"""Fail-closed offline Anisette fallback regression against checked-in Swift UI."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "AltStore/Settings/AnisetteServerList.swift").read_text(encoding="utf8")
MANAGER = (ROOT / "SideStore/Core/Anisette/AnisetteServersManager.swift").read_text(encoding="utf8")

class OfflineAnisetteTests(unittest.TestCase):
    def test_failed_remote_catalog_preserves_local_entries(self):
        failure = SOURCE.split("let isOnline = await AnisetteServersManager.shared.isPublicInternetAvailable()", 1)[1].split("return .failure(error)", 1)[0]
        self.assertIn("self.items = await AnisetteServersManager.shared.loadLocalServers()", failure)
        self.assertNotIn("self.items = []", failure)
        self.assertIn("self.errorMessage = msg", failure)

    def test_ui_displays_saved_servers_during_catalog_outage(self):
        self.assertIn("if viewModel.items.isEmpty {", SOURCE)
        self.assertNotIn("if viewModel.items.isEmpty || viewModel.errorMessage != nil {", SOURCE)
        self.assertIn("Remote Anisette catalog unavailable. Showing saved servers;", SOURCE)
        self.assertIn("UserDefaults.standard.menuAnisetteURL = item.address", SOURCE)

    def test_bundled_windows_server_fallbacks_retained(self):
        self.assertIn('AnisetteServerItem(name: "SideStore (Windows ADI)"', MANAGER)
        self.assertIn('AnisetteServerItem(name: "Jkcoxson (Windows)"', MANAGER)
        self.assertIn("let missingDefaults = Self.defaultInitialServers.filter", MANAGER)

    def test_no_adi_reset_path_in_offline_fallback(self):
        f = SOURCE.split("let isOnline = await AnisetteServersManager.shared.isPublicInternetAvailable()", 1)[1].split("return .failure(error)", 1)[0]
        for forbidden in ("adi.pb", "resetAdi", "signOut", "removeItem(", "Keychain", "revoke"):
            self.assertNotIn(forbidden, f)

if __name__ == "__main__":
    unittest.main()
