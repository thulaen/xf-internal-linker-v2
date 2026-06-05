import importlib.util
import unittest
from pathlib import Path
import tempfile

_MOD_PATH = Path(__file__).resolve().parent / "check-mgmt-command-dry-run.py"
_spec = importlib.util.spec_from_file_location("check_mgmt_command_dry_run", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckMgmtCommandDryRunTests(unittest.TestCase):
    def test_has_dry_run_marker(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as f:
            f.write("# xf: no_dry_run -- reason\n")
            name = f.name
        try:
            self.assertTrue(mod._has_dry_run(Path(name)))
        finally:
            Path(name).unlink()

    def test_has_dry_run_add_argument(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as f:
            f.write("def add_arguments(self, parser):\n    parser.add_argument('--dry-run')\n")
            name = f.name
        try:
            self.assertTrue(mod._has_dry_run(Path(name)))
        finally:
            Path(name).unlink()

    def test_has_dry_run_missing(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".py", delete=False) as f:
            f.write("def add_arguments(self, parser):\n    parser.add_argument('--foo')\n")
            name = f.name
        try:
            self.assertFalse(mod._has_dry_run(Path(name)))
        finally:
            Path(name).unlink()

if __name__ == "__main__":
    unittest.main()
