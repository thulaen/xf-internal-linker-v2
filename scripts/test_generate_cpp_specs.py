import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "generate_cpp_specs.py"
_spec = importlib.util.spec_from_file_location("generate_cpp_specs", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class GenerateCppSpecsTests(unittest.TestCase):
    def test_has_metadata_constants(self):
        # This script mostly orchestrates file writing, so we verify its configuration.
        self.assertTrue(hasattr(mod, "METAS"))
        self.assertTrue(hasattr(mod, "OPTS"))
        self.assertTrue(hasattr(mod, "SAFETY"))
        self.assertTrue(hasattr(mod, "GATES"))
        self.assertGreater(len(mod.METAS), 0)
        self.assertGreater(len(mod.OPTS), 0)

        # Spot check one of the entries
        first_opt = mod.OPTS[0]
        self.assertEqual(first_opt[0], "opt-01-embedding-memory-pool")

if __name__ == "__main__":
    unittest.main()
