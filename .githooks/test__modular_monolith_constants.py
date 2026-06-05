import importlib.util
import unittest
from pathlib import Path
import tempfile

_MOD_PATH = Path(__file__).resolve().parent / "_modular_monolith_constants.py"
_spec = importlib.util.spec_from_file_location("_modular_monolith_constants", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class ModularMonolithConstantsTests(unittest.TestCase):
    def test_go_service_binary_path(self):
        folder = Path("/services/foo")
        self.assertEqual(mod.go_service_binary_path(folder).as_posix(), "/services/foo/cmd/foo/main.go")

    def test_go_service_contract_paths(self):
        folder = Path("/services/foo")
        paths = mod.go_service_contract_paths(folder)
        self.assertEqual(len(paths), 2)
        self.assertEqual(paths[0].as_posix(), "/services/foo/api.proto")
        self.assertEqual(paths[1].as_posix(), "/services/foo/api.http.md")

if __name__ == "__main__":
    unittest.main()
