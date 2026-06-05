import importlib.util
import unittest
from pathlib import Path
import tempfile
import json
import sys

_MOD_PATH = Path(__file__).resolve().parent / "check-bundle-size.py"
_spec = importlib.util.spec_from_file_location("check_bundle_size", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckBundleSizeTests(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(mod._fmt(2048), "2 KB (2,048 bytes)")

    def test_read_baseline_not_exists(self):
        with tempfile.TemporaryDirectory() as d:
            mod.BASELINE_PATH = Path(d) / ".bundle-size-baseline.json"
            self.assertIsNone(mod._read_baseline())

    def test_read_baseline_valid(self):
        with tempfile.TemporaryDirectory() as d:
            mod.BASELINE_PATH = Path(d) / ".bundle-size-baseline.json"
            mod.BASELINE_PATH.write_text(json.dumps({"bytes": 12345}))
            self.assertEqual(mod._read_baseline(), 12345)

    def test_write_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            mod.BASELINE_PATH = Path(d) / ".bundle-size-baseline.json"
            mod._write_baseline(9999)
            self.assertTrue(mod.BASELINE_PATH.exists())
            self.assertEqual(json.loads(mod.BASELINE_PATH.read_text())["bytes"], 9999)

if __name__ == "__main__":
    unittest.main()
