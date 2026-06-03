import importlib.util
import unittest
from pathlib import Path
import tempfile
import hashlib

_MOD_PATH = Path(__file__).resolve().parent / "write_quality_evidence.py"
_spec = importlib.util.spec_from_file_location("write_quality_evidence", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class WriteQualityEvidenceTests(unittest.TestCase):
    def test_optional_float(self):
        self.assertIsNone(mod._optional_float(""))
        self.assertEqual(mod._optional_float("3.14"), 3.14)

    def test_raw_report_text(self):
        self.assertEqual(mod._raw_report_text(None), "")
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
            f.write("hello world")
            name = f.name
        try:
            self.assertEqual(mod._raw_report_text(Path(name)), "hello world")
        finally:
            Path(name).unlink()

    def test_source_hash(self):
        self.assertEqual(mod._source_hash("provided_hash", "path"), "provided_hash")
        self.assertEqual(mod._source_hash("", ""), "")
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(b"data")
            name = f.name
        try:
            expected = hashlib.sha256(b"data").hexdigest()
            self.assertEqual(mod._source_hash("", name), expected)
        finally:
            Path(name).unlink()

if __name__ == "__main__":
    unittest.main()
