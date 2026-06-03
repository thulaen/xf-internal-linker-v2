import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_MOD_PATH = Path(__file__).resolve().parent / "verify_unused_python.py"
_spec = importlib.util.spec_from_file_location("verify_unused_python", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class VerifyUnusedPythonTests(unittest.TestCase):
    @patch("subprocess.run")
    def test_has_importer_found(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "some/file.py:from .my_service import foo\n"
        mock_run.return_value = mock_result
        
        self.assertTrue(mod._has_importer("my_service"))

    @patch("subprocess.run")
    def test_has_importer_not_found(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_run.return_value = mock_result
        
        self.assertFalse(mod._has_importer("my_service"))

    @patch("subprocess.run")
    def test_has_importer_fallback_on_git_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        # Fallback assumes importer exists if git is unavailable
        self.assertTrue(mod._has_importer("my_service"))

if __name__ == "__main__":
    unittest.main()
