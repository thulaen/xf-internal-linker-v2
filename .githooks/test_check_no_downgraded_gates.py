import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-no-downgraded-gates.py"
_spec = importlib.util.spec_from_file_location("check_no_downgraded_gates", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckNoDowngradedGatesTests(unittest.TestCase):
    def test_added_lines(self):
        diff = """--- a/file
+++ b/file
@@ -1,2 +1,3 @@
 context
+added line
-removed line
+another added
"""
        self.assertEqual(mod.added_lines(diff), ["added line", "another added"])

    def test_justification_re(self):
        self.assertTrue(mod.JUSTIFICATION_RE.search("# GATE-DOWNGRADE-JUSTIFICATION: some long reason here"))
        self.assertFalse(mod.JUSTIFICATION_RE.search("# GATE-DOWNGRADE-JUSTIFICATION: short"))

if __name__ == "__main__":
    unittest.main()
