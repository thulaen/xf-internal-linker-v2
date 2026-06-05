import importlib.util
import sys
import unittest
from pathlib import Path
import ast

_MOD_PATH = Path(__file__).resolve().parent / "check-forbidden-patterns.py"
_spec = importlib.util.spec_from_file_location("check_forbidden_patterns", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
# Register before exec so the module's @dataclass can resolve its own
# __module__ via sys.modules (Python 3.12 dataclasses requirement).
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

class CheckForbiddenPatternsTests(unittest.TestCase):
    def test_has_noqa(self):
        source_lines = ["", "foo()", "bar()  # noqa: forbidden-pattern"]
        self.assertTrue(mod._has_noqa(source_lines, 3, window=0))
        self.assertFalse(mod._has_noqa(source_lines, 2, window=0))

    def test_scan_unscoped_todo(self):
        source = "\n".join(["", "# TO" "DO: fix this", "# FIX" "ME(RPT-123): fix that", "        "])
        lines = source.splitlines()
        violations = mod.scan_unscoped_todo(source, lines, Path("foo.py"))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].lineno, 2)

    def test_scan_silent_except(self):
        source = """
try:
    pass
except Exception:
    pass
        """
        lines = source.splitlines()
        tree = ast.parse(source)
        violations = mod.scan_silent_except(tree, lines, Path("foo.py"))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].lineno, 4)

if __name__ == "__main__":
    unittest.main()
