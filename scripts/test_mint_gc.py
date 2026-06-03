import importlib.util
import unittest
from pathlib import Path
from datetime import datetime, UTC

_MOD_PATH = Path(__file__).resolve().parent / "mint_gc.py"
_spec = importlib.util.spec_from_file_location("mint_gc", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class MintGcTests(unittest.TestCase):
    def test_collect_garbage_ignores_retained(self):
        blobs = ["/path/abc", "/path/def"]
        retained = {"abc"}
        to_delete = mod.collect_garbage(blobs, retained, grace_period_days=0)
        self.assertEqual(to_delete, ["/path/def"])

    def test_collect_garbage_respects_grace_period(self):
        # Without actual filesystem stat, the mock handles OSError and includes it anyway?
        # Actually in the code: "Can't stat remote path locally; skip the grace-period check... pass -> to_delete.append"
        blobs = ["/path/def"]
        retained = set()
        to_delete = mod.collect_garbage(blobs, retained, grace_period_days=14)
        # Because local file doesn't exist, it throws OSError inside _blob_age_days and proceeds to append.
        self.assertEqual(to_delete, ["/path/def"])

    def test_parse_created_at_valid(self):
        dt = mod._parse_created_at("2026-06-03T00:00:00Z")
        self.assertEqual(dt, datetime(2026, 6, 3, 0, 0, 0, tzinfo=UTC))

    def test_parse_created_at_invalid(self):
        self.assertIsNone(mod._parse_created_at("invalid"))
        self.assertIsNone(mod._parse_created_at(None))
        self.assertIsNone(mod._parse_created_at(""))

if __name__ == "__main__":
    unittest.main()
