import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-lua-test-isolation.py"
_spec = importlib.util.spec_from_file_location("check_lua_test_isolation", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckLuaTestIsolationTests(unittest.TestCase):
    def test_structure(self):
        self.assertTrue(hasattr(mod, "main"))
        self.assertTrue(hasattr(mod, "_candidates"))

if __name__ == "__main__":
    unittest.main()
