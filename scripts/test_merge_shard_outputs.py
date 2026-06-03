import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "merge_shard_outputs.py"
_spec = importlib.util.spec_from_file_location("merge_shard_outputs", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class MergeShardOutputsTests(unittest.TestCase):
    def test_check_manifests_returns_empty_when_all_present(self):
        entries = [{"required_for_merge": True, "sha256": "abc"}]
        errors = mod.check_manifests(entries, lambda sha: True)
        self.assertEqual(errors, [])

    def test_check_manifests_reports_missing_blob(self):
        entries = [{"required_for_merge": True, "sha256": "abc", "logical_path": "a/b"}]
        errors = mod.check_manifests(entries, lambda sha: False)
        self.assertEqual(len(errors), 1)
        self.assertIn("Missing required blob sha256=abc", errors[0])

    def test_check_manifests_ignores_unrequired(self):
        entries = [{"required_for_merge": False, "sha256": "abc"}]
        errors = mod.check_manifests(entries, lambda sha: False)
        self.assertEqual(errors, [])

    def test_check_failed_shards_reports_missing_autoissue(self):
        entries = [{"required_for_merge": True, "failed": True, "shard_id": "s1", "tool": "t1"}]
        errors = mod.check_failed_shards(entries)
        self.assertEqual(len(errors), 1)
        self.assertIn("has no autoissue_id", errors[0])

    def test_check_failed_shards_ok_with_autoissue(self):
        entries = [{"required_for_merge": True, "failed": True, "autoissue_id": 123}]
        errors = mod.check_failed_shards(entries)
        self.assertEqual(errors, [])

    def test_check_failed_shards_ignores_not_failed(self):
        entries = [{"required_for_merge": True, "failed": False}]
        errors = mod.check_failed_shards(entries)
        self.assertEqual(errors, [])

if __name__ == "__main__":
    unittest.main()
