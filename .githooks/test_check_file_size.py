import importlib.util
import unittest
from pathlib import Path
import tempfile

_MOD_PATH = Path(__file__).resolve().parent / "check-file-size.py"
_spec = importlib.util.spec_from_file_location("check_file_size", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckFileSizeTests(unittest.TestCase):
    def test_is_watched(self):
        self.assertTrue(mod.is_watched("backend/apps/core/models.py"))
        self.assertTrue(mod.is_watched("frontend/src/app/app.component.ts"))
        self.assertFalse(mod.is_watched("frontend/src/app/api/schema.d.ts")) # exempt
        self.assertFalse(mod.is_watched("backend/apps/core/data.json")) # untracked extension

    def test_line_count(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".py") as f:
            f.write("a\nb\nc\n")
            name = f.name
        try:
            self.assertEqual(mod.line_count(name), 3)
        finally:
            Path(name).unlink()

if __name__ == "__main__":
    unittest.main()
