import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

_MOD_PATH = Path(__file__).resolve().parent / "_auto_log_failure.py"
_spec = importlib.util.spec_from_file_location("_auto_log_failure", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class AutoLogFailureTests(unittest.TestCase):
    @patch("subprocess.run")
    def test_main_calls_subprocess_and_returns_zero(self, mock_run):
        # We test that it successfully swallows errors
        mock_run.side_effect = FileNotFoundError()
        
        # Patch sys.argv
        test_args = ["_auto_log_failure.py", "--hook", "test_hook", "--stderr-snippet", "fail"]
        with patch.object(sys, "argv", test_args):
            result = mod.main()
            self.assertEqual(result, 0)
            mock_run.assert_called_once()

if __name__ == "__main__":
    unittest.main()
