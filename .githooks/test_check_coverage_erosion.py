import importlib.util
import unittest
from pathlib import Path
import tempfile
import json
import sys

_MOD_PATH = Path(__file__).resolve().parent / "check-coverage-erosion.py"
_spec = importlib.util.spec_from_file_location("check_coverage_erosion", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckCoverageErosionTests(unittest.TestCase):
    def test_read_baseline_not_exists(self):
        with tempfile.TemporaryDirectory() as d:
            mod.BASELINE_PATH = Path(d) / ".coverage-baseline.json"
            self.assertIsNone(mod._read_baseline())

    def test_read_baseline_valid(self):
        with tempfile.TemporaryDirectory() as d:
            mod.BASELINE_PATH = Path(d) / ".coverage-baseline.json"
            mod.BASELINE_PATH.write_text(json.dumps({"percent_covered": 85.5}))
            self.assertEqual(mod._read_baseline(), 85.5)

    def test_write_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            mod.BASELINE_PATH = Path(d) / ".coverage-baseline.json"
            mod._write_baseline(90.123)
            self.assertTrue(mod.BASELINE_PATH.exists())
            self.assertEqual(json.loads(mod.BASELINE_PATH.read_text())["percent_covered"], 90.12)

if __name__ == "__main__":
    unittest.main()
