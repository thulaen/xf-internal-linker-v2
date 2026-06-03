import importlib.util
import unittest
from pathlib import Path
import os
from unittest.mock import patch

_MOD_PATH = Path(__file__).resolve().parent / "windows_storage.py"
_spec = importlib.util.spec_from_file_location("windows_storage", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class WindowsStorageTests(unittest.TestCase):
    @patch.dict(os.environ, {"TEMP": r"C:\Users\tester\AppData\Local\Temp"}, clear=True)
    def test_validate_safe_delete_path_temp(self):
        # Should not raise
        mod.validate_safe_delete_path(r"C:\Users\tester\AppData\Local\Temp\foo.txt")

    def test_validate_safe_delete_path_c_xf(self):
        # Should not raise
        mod.validate_safe_delete_path(r"c:\xf\myproject\build")

    def test_validate_safe_delete_path_unsafe(self):
        with self.assertRaises(ValueError):
            mod.validate_safe_delete_path(r"C:\Windows\System32\cmd.exe")

    def test_check_storage_caps_ok(self):
        caps = {r"C:\xf\test": 1024}
        warnings = mod.check_storage_caps(caps, get_used_bytes=lambda _: 500)
        self.assertEqual(warnings, [])

    def test_check_storage_caps_exceeded(self):
        caps = {r"C:\xf\test": 1024}
        warnings = mod.check_storage_caps(caps, get_used_bytes=lambda _: 2048)
        self.assertEqual(len(warnings), 1)
        self.assertIn("WARNING: C:\\xf\\test used", warnings[0])

if __name__ == "__main__":
    unittest.main()
