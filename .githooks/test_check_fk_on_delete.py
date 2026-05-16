#!/usr/bin/env python3
"""Tests for check-fk-on-delete.py (Rule H.H22)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock


def _load_hook():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "check_fk_on_delete", here / "check-fk-on-delete.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckFkOnDeleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def _scan_text(self, text: str):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "models.py"
            f.write_text(text, encoding="utf-8")
            return self.hook._scan(f)

    def test_no_files_passes(self):
        with mock.patch.object(self.hook, "_staged_models_files", return_value=[]):
            self.assertEqual(self.hook.main(), 0)

    def test_fk_with_on_delete_passes(self):
        hits = self._scan_text(
            "from django.db import models\n"
            "class A(models.Model):\n"
            "    parent = models.ForeignKey('self', on_delete=models.CASCADE)\n"
        )
        self.assertEqual(hits, [])

    def test_fk_without_on_delete_flagged(self):
        hits = self._scan_text(
            "from django.db import models\n"
            "class A(models.Model):\n"
            "    parent = models.ForeignKey('self', null=True)\n"
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], "ForeignKey")

    def test_onetoone_without_on_delete_flagged(self):
        hits = self._scan_text(
            "from django.db import models\n"
            "class A(models.Model):\n"
            "    parent = models.OneToOneField('B')\n"
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], "OneToOneField")

    def test_main_emits_plain_english_fail(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "backend/apps/x/models.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "from django.db import models\n"
                "class A(models.Model):\n"
                "    parent = models.ForeignKey('self')\n",
                encoding="utf-8",
            )
            with mock.patch.object(self.hook, "REPO_ROOT", Path(td)), \
                 mock.patch.object(self.hook, "_staged_models_files",
                                   return_value=[path]), \
                 mock.patch.object(sys, "stderr", StringIO()) as err:
                self.assertEqual(self.hook.main(), 2)
                msg = err.getvalue()
                self.assertIn("FAIL", msg)
                self.assertIn("WHY", msg)
                self.assertIn("UNBLOCK", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
