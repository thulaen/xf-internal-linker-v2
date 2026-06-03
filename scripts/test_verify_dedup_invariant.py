import importlib.util
import unittest
from pathlib import Path

# Mock django before loading
import sys
from unittest.mock import MagicMock
sys.modules['django'] = MagicMock()
sys.modules['apps.core.services.self_test_smoke'] = MagicMock()

_MOD_PATH = Path(__file__).resolve().parent / "verify_dedup_invariant.py"
_spec = importlib.util.spec_from_file_location("verify_dedup_invariant", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class VerifyDedupInvariantTests(unittest.TestCase):
    def test_module_structure(self):
        # We can't easily test main without mocking the full Django startup which we did above,
        # but let's at least check that main exists and the environment variable is set.
        self.assertTrue(hasattr(mod, "main"))
        import os
        self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "config.settings.test")

if __name__ == "__main__":
    unittest.main()
