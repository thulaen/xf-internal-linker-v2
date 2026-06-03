"""
Tests for scripts/windows_storage.py

BDD:
  Given the safe-delete path validator
  When a path outside C:\\xf\\ and %TEMP% is passed
  Then validate_safe_delete_path() raises ValueError

  Given a path under C:\\xf\\ or %TEMP%
  When validate_safe_delete_path() is called
  Then no exception is raised

  Given the storage-cap checker
  When a root's used size exceeds its cap
  Then check_storage_caps() returns a warning (non-empty list of strings)
  And it does not raise an exception
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "windows_storage.py"


def _load():
    spec = importlib.util.spec_from_file_location("windows_storage", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["windows_storage"] = mod
    spec.loader.exec_module(mod)
    return mod


try:
    ws = _load()
except FileNotFoundError:
    ws = None


class TestValidateSafeDeletePath(TestCase):

    def setUp(self):
        if ws is None:
            self.skipTest("windows_storage.py not yet written")

    def test_raises_for_path_outside_safe_roots(self):
        with self.assertRaises(ValueError):
            ws.validate_safe_delete_path(r"C:\Users\goldm\source\important.py")

    def test_raises_for_c_root(self):
        with self.assertRaises(ValueError):
            ws.validate_safe_delete_path(r"C:\\")

    def test_raises_for_desktop_path(self):
        with self.assertRaises(ValueError):
            ws.validate_safe_delete_path(r"C:\Users\goldm\Desktop\file.txt")

    def test_allows_cxf_path(self):
        ws.validate_safe_delete_path(r"C:\xf\temp-runs\run-001\results.json")

    def test_allows_cxf_subpath(self):
        ws.validate_safe_delete_path(r"C:\xf\tool-cache\go\bin\go.exe")

    def test_allows_temp_path(self):
        temp = r"C:\Users\goldm\AppData\Local\Temp"
        with mock.patch.dict(os.environ, {"TEMP": temp}):
            ws.validate_safe_delete_path(temp + r"\xf-artifact.json")

    def test_allows_temp_path_case_insensitive(self):
        temp = r"C:\Users\goldm\AppData\Local\Temp"
        with mock.patch.dict(os.environ, {"TEMP": temp}):
            ws.validate_safe_delete_path(temp.upper() + r"\xf-artifact.json")

    def test_raises_for_c_xf_without_slash(self):
        # "C:\xfoo" must NOT be treated as a match for "C:\xf\"
        with self.assertRaises(ValueError):
            ws.validate_safe_delete_path(r"C:\xfoo\evil.py")

    def test_error_message_names_path(self):
        bad_path = r"C:\Users\goldm\secret.txt"
        try:
            ws.validate_safe_delete_path(bad_path)
        except ValueError as exc:
            self.assertIn(bad_path, str(exc))
        else:
            self.fail("Expected ValueError was not raised")


class TestCheckStorageCaps(TestCase):

    def setUp(self):
        if ws is None:
            self.skipTest("windows_storage.py not yet written")

    def test_returns_list(self):
        caps = {"C:\\xf\\temp-runs": 1}  # 1 byte cap
        result = ws.check_storage_caps(caps, get_used_bytes=lambda p: 0)
        self.assertIsInstance(result, list)

    def test_no_warnings_when_under_cap(self):
        caps = {r"C:\xf\temp-runs": 2 * 1024 ** 3}  # 2 GB cap
        result = ws.check_storage_caps(caps, get_used_bytes=lambda p: 0)
        self.assertEqual(result, [])

    def test_warning_when_over_cap(self):
        cap_bytes = 1024 ** 3  # 1 GB cap
        caps = {r"C:\xf\temp-runs": cap_bytes}
        # Report usage at 2× cap
        result = ws.check_storage_caps(
            caps, get_used_bytes=lambda p: cap_bytes * 2
        )
        self.assertGreater(len(result), 0)

    def test_warning_is_string(self):
        cap_bytes = 1024 ** 3
        caps = {r"C:\xf\temp-runs": cap_bytes}
        warnings = ws.check_storage_caps(
            caps, get_used_bytes=lambda p: cap_bytes * 2
        )
        for w in warnings:
            with self.subTest(w=w):
                self.assertIsInstance(w, str)

    def test_does_not_raise_when_over_cap(self):
        """Cap exceeded → warning, not an exception."""
        cap_bytes = 100
        caps = {r"C:\xf\temp-runs": cap_bytes}
        try:
            ws.check_storage_caps(caps, get_used_bytes=lambda p: cap_bytes * 100)
        except Exception as exc:
            self.fail(f"check_storage_caps should not raise, but raised: {exc}")

    def test_warning_names_the_path(self):
        cap_bytes = 1024
        caps = {r"C:\xf\temp-runs": cap_bytes}
        warnings = ws.check_storage_caps(
            caps, get_used_bytes=lambda p: cap_bytes * 2
        )
        self.assertTrue(
            any(r"C:\xf\temp-runs" in w for w in warnings),
            "Warning should name the exceeded path",
        )

    def test_multiple_roots(self):
        caps = {
            r"C:\xf\temp-runs": 1024,
            r"C:\xf\tool-cache": 1024,
        }
        # Both over cap
        warnings = ws.check_storage_caps(caps, get_used_bytes=lambda p: 999999)
        self.assertGreaterEqual(len(warnings), 2)
