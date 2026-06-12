"""Tests for verify_codeql_autoissues management command."""

from unittest import mock
from io import StringIO

from django.test import SimpleTestCase
from django.core.management import call_command
from django.core.management.base import CommandError


class VerifyCodeqlAutoissuesTests(SimpleTestCase):
    @mock.patch("apps.auto_issues.management.commands.verify_codeql_autoissues.codeql.verify_codeql_autoissues")
    def test_given_under_quota_when_run_then_passes(self, mock_verify):
        mock_verify.return_value = [1, 2]
        out = StringIO()
        call_command("verify_codeql_autoissues", "--max-open=5", stdout=out)
        self.assertIn("[CODEQL AUTOISSUES VERIFIED: open=2 max=5]", out.getvalue())

    @mock.patch("apps.auto_issues.management.commands.verify_codeql_autoissues.codeql.verify_codeql_autoissues")
    def test_given_over_quota_when_run_then_raises_error(self, mock_verify):
        mock_verify.side_effect = ValueError("Too many CodeQL issues open")
        with self.assertRaisesMessage(CommandError, "Too many CodeQL issues open"):
            call_command("verify_codeql_autoissues", "--max-open=5", "--block-open")
