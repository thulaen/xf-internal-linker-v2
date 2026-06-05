import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-lua-test-sandbox.py"
_spec = importlib.util.spec_from_file_location("check_lua_test_sandbox", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckLuaTestSandboxTests(unittest.TestCase):
    def test_forbidden_patterns(self):
        self.assertTrue(mod.FORBIDDEN["io"].search("io.open('foo')"))
        self.assertTrue(mod.FORBIDDEN["os"].search("os.execute('rm')"))
        self.assertTrue(mod.FORBIDDEN["require"].search("require('string')"))
        
        # Allowed ones
        self.assertFalse(mod.FORBIDDEN["io"].search("local x = foo.io.open"))
        self.assertFalse(mod.FORBIDDEN["os"].search("local os = 1"))

if __name__ == "__main__":
    unittest.main()
