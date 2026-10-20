import unittest
from patch_iloader_xctest import ORIGINAL, REPLACEMENT, transform


class XCTestBundleIdTests(unittest.TestCase):
    def test_equal_xctest_ids_become_same_signed_id(self):
        root = "com.openminis.ictrl.uitests.xctrunner"
        a, b = transform(root, root, "xctest", "5MT7S99K8V")
        self.assertEqual(a, b)
        self.assertEqual(a, root + ".5MT7S99K8V")

    def test_other_extensions_keep_prior_behavior(self):
        a, b = transform("com.example.app", "com.example.app.Share", "appex", "TEAM")
        self.assertEqual(b, a + ".Share")

    def test_equal_non_xctest_rejected(self):
        with self.assertRaises(ValueError):
            transform("com.example.app", "com.example.app", "appex", "TEAM")

    def test_double_suffix_is_not_created_for_equal_id(self):
        a, b = transform("com.example.app", "com.example.app", "xctest", "TEAM")
        self.assertNotIn(".TEAM.TEAM", a + "|" + b)

    def test_patched_source_is_narrow(self):
        self.assertIn('Some("xctest")', REPLACEMENT)
        self.assertIn('id == main_app_bundle_id', REPLACEMENT)
        self.assertIn('id.len() > main_app_bundle_id.len()', REPLACEMENT)
        self.assertIn('id.len() > main_app_bundle_id.len()', ORIGINAL)


if __name__ == "__main__":
    unittest.main()
