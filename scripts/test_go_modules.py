import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "go_modules.py"
_spec = importlib.util.spec_from_file_location("go_modules", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class GoModulesTests(unittest.TestCase):
    def test_constants_defined(self):
        self.assertIn(".go", mod.GO_EXTENSIONS)
        self.assertIn("go.mod", mod.GO_MOD_FILES)
        self.assertIn(".proto", mod.PROTO_EXTENSIONS)
        self.assertTrue(hasattr(mod, "IGNORED_DIRS"))

    def test_modules_for_paths_skips_unrelated_extensions(self):
        # Even without mocking file system, passing an irrelevant extension should return [] immediately
        result = mod._modules_for_paths(["README.md", "image.png"])
        self.assertEqual(result, [])

if __name__ == "__main__":
    unittest.main()
