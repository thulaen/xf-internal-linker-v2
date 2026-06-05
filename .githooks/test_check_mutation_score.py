import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-mutation-score.py"
_spec = importlib.util.spec_from_file_location("check_mutation_score", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckMutationScoreTests(unittest.TestCase):
    def test_mutmut_score(self):
        data = [
            {"status": "killed"},
            {"status": "survived"},
            {"status": "killed"}
        ]
        self.assertAlmostEqual(mod._mutmut_score(data), 66.666, places=2)

    def test_stryker_score_direct(self):
        data = {"mutationScore": 85.5}
        self.assertEqual(mod._stryker_score(data), 85.5)

    def test_stryker_score_computed(self):
        data = {
            "files": {
                "a": {"mutants": [{"status": "Killed"}, {"status": "Survived"}]},
                "b": {"mutants": [{"status": "Timeout"}]}
            }
        }
        self.assertAlmostEqual(mod._stryker_score(data), 66.666, places=2)

    def test_mull_score(self):
        data = {"mutationScore": 90.0}
        self.assertEqual(mod._mull_score(data), 90.0)

if __name__ == "__main__":
    unittest.main()
