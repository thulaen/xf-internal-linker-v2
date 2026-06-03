import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check_quality_report.py"
_spec = importlib.util.spec_from_file_location("check_quality_report", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckQualityReportTests(unittest.TestCase):
    def test_angular_metric_extracts_pct(self):
        data = {"total": {"lines": {"pct": 95.5}}}
        self.assertEqual(mod._angular_metric(data, "lines"), 95.5)

    def test_angular_metric_raises_if_missing(self):
        with self.assertRaises(RuntimeError) as cm:
            mod._angular_metric({}, "lines")
        self.assertEqual(str(cm.exception), "Missing Angular coverage metric: lines")

    def test_mutation_score_stryker(self):
        data = {"mutationScore": 85.5}
        self.assertEqual(mod._mutation_score(data, "stryker"), 85.5)

    def test_mutation_score_list_of_mutants(self):
        data = [
            {"status": "killed"},
            {"status": "Timeout"},
            {"status": "Survived"},
            {"status": "Killed"}
        ]
        self.assertEqual(mod._mutation_score(data, "mull"), 75.0)

    def test_mutation_score_dict_with_mutants_key(self):
        data = {"mutants": [{"status": "killed"}, {"status": "Survived"}]}
        self.assertEqual(mod._mutation_score(data, "mutmut"), 50.0)

    def test_mutation_score_raises_if_missing_mutants(self):
        with self.assertRaises(RuntimeError) as cm:
            mod._mutation_score({"mutants": []}, "mutmut")
        self.assertEqual(str(cm.exception), "Missing mutation data for mutmut")

if __name__ == "__main__":
    unittest.main()
