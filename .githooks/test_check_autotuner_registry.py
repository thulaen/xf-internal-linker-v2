import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-autotuner-registry.py"
_spec = importlib.util.spec_from_file_location("check_autotuner_registry", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckAutotunerRegistryTests(unittest.TestCase):
    def test_is_tunable(self):
        self.assertTrue(mod._is_tunable("pipeline.foo"))
        self.assertTrue(mod._is_tunable("score_bar"))
        self.assertTrue(mod._is_tunable("w_baz"))
        self.assertTrue(mod._is_tunable("ranking.w_qux"))
        self.assertFalse(mod._is_tunable("foo.bar"))

    def test_exclusion_re(self):
        self.assertTrue(mod.EXCLUSION_RE.search("foo\\n# AUTOTUNER-EXCLUDED: reason\\nbar"))
        self.assertFalse(mod.EXCLUSION_RE.search("foo\\n# NOT-EXCLUDED: reason\\nbar"))

if __name__ == "__main__":
    unittest.main()
