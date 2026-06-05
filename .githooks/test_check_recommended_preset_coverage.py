import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-recommended-preset-coverage.py"
_spec = importlib.util.spec_from_file_location("check_recommended_preset_coverage", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckRecommendedPresetCoverageTests(unittest.TestCase):
    def test_is_tunable(self):
        self.assertTrue(mod._is_tunable("pipeline.foo"))
        self.assertTrue(mod._is_tunable("score_bar"))
        self.assertFalse(mod._is_tunable("foo.bar"))

    def test_exclusion_re(self):
        self.assertTrue(mod.EXCLUSION_RE.search("# AUTOTUNER-EXCLUDED: reason"))

    def test_weightpreset_upsert_re(self):
        self.assertTrue(mod.WEIGHTPRESET_UPSERT_RE.search("WeightPreset.objects.update_or_create(name='Recommended')"))

if __name__ == "__main__":
    unittest.main()
