import importlib.util
import unittest
from pathlib import Path
import tempfile

_MOD_PATH = Path(__file__).resolve().parent / "check-missing-tests.py"
_spec = importlib.util.spec_from_file_location("check_missing_tests", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckMissingTestsTests(unittest.TestCase):
    def test_file_exists_anywhere(self):
        staged = {"backend/apps/core/tests_settings_helpers.py"}
        # Already staged
        self.assertTrue(mod.file_exists_anywhere(["backend/apps/core/tests_settings_helpers.py"], staged))
        # Doesn't exist
        self.assertFalse(mod.file_exists_anywhere(["backend/apps/core/test_nonexistent.py"], staged))

    def test_frontend_new_re(self):
        self.assertTrue(mod.FRONTEND_NEW_RE.match("frontend/src/app/foo.component.ts"))
        self.assertTrue(mod.FRONTEND_NEW_RE.match("frontend/src/app/foo.service.ts"))
        self.assertFalse(mod.FRONTEND_NEW_RE.match("frontend/src/app/foo.model.ts"))

if __name__ == "__main__":
    unittest.main()
