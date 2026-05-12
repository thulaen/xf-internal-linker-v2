"""Tests for the lint_error picker — Phase 6 of the test-hardening plan."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.services import lint_error


class LintErrorPickerTests(SimpleTestCase):
    def test_missing_sarif_file_returns_zero(self) -> None:
        self.assertEqual(lint_error.pick_lint_errors(), 0)

    def test_sarif_severity_mapping(self) -> None:
        self.assertEqual(lint_error._sarif_to_project_severity("error"), "high")
        self.assertEqual(lint_error._sarif_to_project_severity("warning"), "medium")
        self.assertEqual(lint_error._sarif_to_project_severity("note"), "low")
        self.assertEqual(lint_error._sarif_to_project_severity("unknown"), "low")
