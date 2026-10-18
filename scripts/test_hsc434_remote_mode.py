"""Regression gate for the SideStore -> SideSign hsc=434 remote mode handoff."""

import re
import unittest
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "SideStore" / "Core" / "Anisette" / "AnisetteProvider.swift"
)


class RemoteAnisetteModeRegression(unittest.TestCase):
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
        # This fix must not add a second ADI mutation. Existing upstream
        # recovery, which may purge on -45061, remains unchanged.
        self.assertEqual(text.count("anisetteAdiBlob = nil"), 2)
        self.assertNotIn("clearSignInInfo(", text)
        self.assertNotIn("clearActiveCertificate(", text)


if __name__ == "__main__":
    unittest.main()
