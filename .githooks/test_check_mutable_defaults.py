import importlib.util
import sys
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-mutable-defaults.py"
_spec = importlib.util.spec_from_file_location("check_mutable_defaults", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

class CheckMutableDefaultsTests(unittest.TestCase):
    def test_structure(self):
        self.assertTrue(hasattr(mod, "main"))
        self.assertTrue(hasattr(mod, "_find_mutable_defaults"))

    def test_finds_list_default(self):
        findings = mod._find_mutable_defaults("example.py", "def bad(items=[]):\n    return items\n")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].label, "list literal []")

    def test_allows_none_default(self):
        findings = mod._find_mutable_defaults(
            "example.py",
            "def good(items=None):\n    return [] if items is None else items\n",
        )

        self.assertEqual(findings, [])

    def test_honors_noqa_b006(self):
        findings = mod._find_mutable_defaults(
            "example.py",
            "def intentional(items=[]):  # noqa: B006\n    return items\n",
        )

        self.assertEqual(findings, [])

if __name__ == "__main__":
    unittest.main()
