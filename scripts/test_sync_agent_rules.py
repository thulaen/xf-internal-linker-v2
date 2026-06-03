import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "sync_agent_rules.py"
_spec = importlib.util.spec_from_file_location("sync_agent_rules", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)

# This script imports from `_rules_sync_helpers` which is in the same directory.
import sys
from unittest.mock import MagicMock
sys.modules['_rules_sync_helpers'] = MagicMock()

_spec.loader.exec_module(mod)

class SyncAgentRulesTests(unittest.TestCase):
    def test_functions_exist(self):
        # The script orchestrates calls to _rules_sync_helpers, so we just verify the structure
        self.assertTrue(hasattr(mod, "check"))
        self.assertTrue(hasattr(mod, "verify_plan_rules"))
        self.assertTrue(hasattr(mod, "verify_forbidden_phrases"))
        self.assertTrue(hasattr(mod, "apply_from"))
        self.assertTrue(hasattr(mod, "main"))

if __name__ == "__main__":
    unittest.main()
