import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check_quality_policy.py"
_spec = importlib.util.spec_from_file_location("check_quality_policy", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckQualityPolicyTests(unittest.TestCase):
    def test_coverage_key(self):
        self.assertEqual(mod._coverage_key("frontend/src/app/app.component.ts"), "/repo/frontend/src/app/app.component.ts")

    def test_legacy_coverage_key(self):
        self.assertEqual(mod._legacy_coverage_key("frontend/src/app/app.component.ts"), "/app/src/app/app.component.ts")

    def test_baseline_metric_extracts_value(self):
        baseline = {"path/to/file": {"lines": 85.5}}
        self.assertEqual(mod._baseline_metric(baseline, "path/to/file", "lines"), 85.5)

    def test_baseline_metric_returns_none_if_missing(self):
        self.assertIsNone(mod._baseline_metric({}, "path/to/file", "lines"))
        self.assertIsNone(mod._baseline_metric({"path/to/file": {}}, "path/to/file", "lines"))

    def test_check_existing_metric_meets_target(self):
        ok, msg = mod._check_existing_metric(baseline={}, path="file.ts", metric_name="lines", target=90.0, actual=95.0)
        self.assertTrue(ok)
        self.assertEqual(msg, "file.ts lines meets the full target.")

    def test_check_existing_metric_no_baseline(self):
        ok, msg = mod._check_existing_metric(baseline={}, path="file.ts", metric_name="lines", target=90.0, actual=80.0)
        self.assertFalse(ok)
        self.assertEqual(msg, "file.ts lines is 80.0%, below 90.0%, and has no ratchet baseline.")

    def test_check_existing_metric_dropped(self):
        baseline = {"file.ts": {"lines": 85.0}}
        ok, msg = mod._check_existing_metric(baseline=baseline, path="file.ts", metric_name="lines", target=90.0, actual=80.0)
        self.assertFalse(ok)
        self.assertEqual(msg, "file.ts lines dropped from 85.0% to 80.0%.")

    def test_check_existing_metric_improved_but_below_target(self):
        baseline = {"file.ts": {"lines": 80.0}}
        ok, msg = mod._check_existing_metric(baseline=baseline, path="file.ts", metric_name="lines", target=90.0, actual=85.0)
        self.assertTrue(ok)
        self.assertEqual(msg, "file.ts lines improved from 80.0% to 85.0%.")
        
    def test_check_existing_metric_stagnant_below_target(self):
        baseline = {"file.ts": {"lines": 80.0}}
        ok, msg = mod._check_existing_metric(baseline=baseline, path="file.ts", metric_name="lines", target=90.0, actual=80.0)
        self.assertFalse(ok)
        self.assertEqual(msg, "file.ts lines is below target and did not improve above the 80.0% baseline.")

if __name__ == "__main__":
    unittest.main()
