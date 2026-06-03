import importlib.util
import unittest
from pathlib import Path

# We must mock codeql_language_inventory since it's imported
import sys
from unittest.mock import MagicMock
sys.modules['codeql_language_inventory'] = MagicMock()
sys.modules['codeql_language_inventory'].build_mode_for_language = lambda l: "none" if l != "go" else "manual"

_MOD_PATH = Path(__file__).resolve().parent / "run_codeql.py"
_spec = importlib.util.spec_from_file_location("run_codeql", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class RunCodeqlTests(unittest.TestCase):
    def test_database_create_args_python(self):
        args = mod._database_create_args("codeql", "python", Path("/db/python"), "4", "4096")
        self.assertIn("codeql", args)
        self.assertIn("--language=python", args)
        self.assertIn("--threads=4", args)
        self.assertIn("--build-mode=none", args)

    def test_database_create_args_go(self):
        args = mod._database_create_args("codeql", "go", Path("/db/go"), "4", "4096")
        self.assertIn("--language=go", args)
        self.assertTrue(any("codeql-build-go.sh" in a for a in args))
        self.assertNotIn("--build-mode=none", args)

    def test_analyze_args(self):
        args = mod._analyze_args("codeql", "python", Path("/db/python"), Path("/out/python.sarif"), "4", "4096")
        self.assertIn("codeql", args)
        self.assertIn(mod.QUERY_SUITES["python"], args)
        self.assertIn("--format=sarifv2.1.0", args)
        self.assertTrue(any("--output=" in a for a in args))

if __name__ == "__main__":
    unittest.main()
