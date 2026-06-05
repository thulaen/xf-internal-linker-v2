import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-luajit-dialect.py"
_spec = importlib.util.spec_from_file_location("check_luajit_dialect", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckLuajitDialectTests(unittest.TestCase):
    def test_forbidden_patterns(self):
        self.assertTrue(mod.FORBIDDEN_PATTERNS["Lua 5.3 integer division"].search("a // b"))
        self.assertFalse(mod.FORBIDDEN_PATTERNS["Lua 5.3 integer division"].search("http://a.com"))
        
        self.assertTrue(mod.FORBIDDEN_PATTERNS["Lua 5.3 bitwise operator"].search("a << b"))
        self.assertTrue(mod.FORBIDDEN_PATTERNS["Lua 5.3 bitwise operator"].search("a ~ b"))
        
        self.assertTrue(mod.FORBIDDEN_PATTERNS["Lua 5.4 close attribute"].search("local f <close> = io.open('a')"))
        self.assertTrue(mod.FORBIDDEN_PATTERNS["Lua 5.3 utf8 library"].search("utf8.len(s)"))
        self.assertFalse(mod.FORBIDDEN_PATTERNS["Lua 5.3 utf8 library"].search("local u = foo.utf8.bar"))

if __name__ == "__main__":
    unittest.main()
