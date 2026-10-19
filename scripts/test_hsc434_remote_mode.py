"""Regression gate for the SideStore -> SideSign hsc=434 remote mode handoff."""

import re
import unittest
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "SideStore" / "Core" / "Anisette" / "AnisetteProvider.swift"
)
CONFIG = (
    Path(__file__).resolve().parents[1]
    / "SideStore" / "Core" / "Anisette" / "AnisetteConfigManager.swift"
)
DEFAULTS = (
    Path(__file__).resolve().parents[1]
    / "AltStore" / "Core" / "Extensions" / "UserDefaults+AltStore.swift"
)


class RemoteAnisetteModeRegression(unittest.TestCase):
    def test_selected_anisette_subdomain_not_rewritten(self):
        source = DEFAULTS.read_text(encoding="utf-8")
        getter = source.split("@objc var menuAnisetteURL:", 1)[1]
        getter = getter.split("@objc var menuAnisetteList:", 1)[0]
        self.assertIn('val == "https://ani.sidestore.io"', getter)
        self.assertNotIn('val.contains("ani.sidestore.io")', getter)
        self.assertIn("return val", getter)

    def test_userdefaults_getter_does_not_discard_pixel_profile(self):
        source = DEFAULTS.read_text(encoding="utf-8")
        getter = source.split("@objc var customAnisetteClientInfo:", 1)[1]
        getter = getter.split("@objc var customAnisetteUserAgent:", 1)[0]
        self.assertIn("self.string(forKey: #function)", getter)
        self.assertIn("return val", getter)
        self.assertNotIn('v.contains("Pixel")', getter)
        self.assertNotIn('v.contains("Android")', getter)
        self.assertIn('v.contains("dt.Xcode")', getter)

    def test_request_headers_uses_configured_profile(self):
        source = CONFIG.read_text(encoding="utf-8")
        section = source.split("public func makeRequestHeaders()", 1)[1]
        section = section.split("public func resolvedXcodeVersion()", 1)[0]
        self.assertIn("let config = loadConfig()", section)
        self.assertIn("$0.clientInfo = config.clientInfo", section)

    def test_provider_exposes_profile_kind_without_logging_secrets(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('effective_client_profile=', source)
        self.assertIn('return "android_custom"', source)
        self.assertIn('return "windows"', source)
        self.assertIn('let clientInfo = headers.clientInfo ?? ""', source)
        self.assertNotIn('headers.clientInfo.contains(', source)
        self.assertNotIn('debugLog(headers)', source)
        self.assertNotIn('debugLog(headers.clientInfo)', source)

    def test_community_pixel_profile_survives_config_load(self):
        text = CONFIG.read_text(encoding="utf-8")
        load = text.split("public func loadConfig()", 1)[1].split("public func makeRequestHeaders()", 1)[0]
        legacy_branch = re.search(
            r"if resolvedClientInfo\.contains\(.+?\)\s*\{"
            r"(?:(?!\n\s*\}).)*?resolvedClientInfo = AppConstants\.Anisette\.defaultClientInfo",
            load, re.DOTALL
        )
        self.assertIsNotNone(legacy_branch)
        self.assertNotIn('"Pixel"', legacy_branch.group(0))
        self.assertNotIn('"Android"', legacy_branch.group(0))
        self.assertIn('"dt.Xcode"', legacy_branch.group(0))
        self.assertIn('ud.customAnisetteClientInfo = resolvedClientInfo', load)

    def test_successful_failover_commits_remote_mode_before_returning(self):
        text = SOURCE.read_text(encoding="utf-8")
        # A fetch(mode: .remote) is temporary; SideSign's resync() later reads
        # the manager's persistent activeMode. Assert the two are bridged.
        pattern = (
            r"onSuccess:\s*\{\s*successfulServer\s+in"
            r"(?:(?!\n\s*\}\s*\)).)*?"
            r"SideSign\.AnisetteDataManager\.shared"
            r"\.setMode\(\.remote\(server:\s*successfulServer\)\)"
            r"(?:(?!\n\s*\}\s*\)).)*?"
            r"menuAnisetteURL\s*=\s*successfulServer\.absoluteString"
        )
        self.assertRegex(text, re.compile(pattern, re.DOTALL))

    def test_mode_not_implicitly_reset_or_adi_destroyed(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertEqual(text.count("setMode(.remote(server: successfulServer))"), 1)
        # Error -45061 and incorrectlyProvisioned must never erase the saved
        # ADI blob as a side effect of automatic server failover.
        self.assertEqual(text.count("anisetteAdiBlob = nil"), 0)
        self.assertIn("Possible ADI desynchronization; preserved local state", text)
        self.assertNotIn("clearSignInInfo(", text)
        self.assertNotIn("clearActiveCertificate(", text)


if __name__ == "__main__":
    unittest.main()
