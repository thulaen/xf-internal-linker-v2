import importlib.util
import unittest
from pathlib import Path
import tempfile
import os

_MOD_PATH = Path(__file__).resolve().parent / "find_untested.py"
_spec = importlib.util.spec_from_file_location("find_untested", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class FindUntestedTests(unittest.TestCase):
    def test_find_untested_components(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # Create a component with a test
            (root / "tested.component.ts").touch()
            (root / "tested.spec.ts").touch()
            
            # Create a component without a test
            (root / "untested.component.ts").touch()
            
            # Create some irrelevant files
            (root / "other.ts").touch()
            
            untested = mod.find_untested_components(d)
            
            self.assertEqual(len(untested), 1)
            self.assertTrue(untested[0].endswith("untested.component.ts"))

if __name__ == "__main__":
    unittest.main()
