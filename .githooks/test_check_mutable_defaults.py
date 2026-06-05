import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-mutable-defaults.py"
_spec = importlib.util.spec_from_file_location("check_mutable_defaults", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckMutableDefaultsTests(unittest.TestCase):
    def test_structure(self):
        self.assertTrue(hasattr(mod, "main"))
        self.assertTrue(hasattr(mod, "_run_ruff"))
        self.assertEqual(mod._RUFF_ARGS, ["check", "--select=B006", "--no-fix"])

if __name__ == "__main__":
    unittest.main()
