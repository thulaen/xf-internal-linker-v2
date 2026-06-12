"""Tests for verify_observability_pipeline management command."""

from unittest import mock
from io import StringIO

from django.test import SimpleTestCase
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.auto_issues.services.observability_pipeline import SourceFreshness


class VerifyObservabilityPipelineTests(SimpleTestCase):
    @mock.patch("apps.auto_issues.management.commands.verify_observability_pipeline.op.pipeline_freshness")
    def test_given_all_sources_active_when_strict_then_passes(self, mock_freshness):
        mock_freshness.return_value = [
            SourceFreshness("source_1", recent_count=10, is_silent=False),
            SourceFreshness("source_2", recent_count=5, is_silent=False),
        ]
        out = StringIO()
        call_command("verify_observability_pipeline", "--strict", stdout=out)
        self.assertIn("source_1: 10 recent", out.getvalue())
        self.assertIn("source_2: 5 recent", out.getvalue())

    @mock.patch("apps.auto_issues.management.commands.verify_observability_pipeline.op.pipeline_freshness")
    def test_given_silent_source_when_not_strict_then_warns_only(self, mock_freshness):
        mock_freshness.return_value = [
            SourceFreshness("source_1", recent_count=0, is_silent=True),
        ]
        out = StringIO()
        call_command("verify_observability_pipeline", stdout=out)
        self.assertIn("source_1: SILENT", out.getvalue())

    @mock.patch("apps.auto_issues.management.commands.verify_observability_pipeline.op.pipeline_freshness")
    def test_given_silent_source_when_strict_then_raises_error(self, mock_freshness):
        mock_freshness.return_value = [
            SourceFreshness("source_1", recent_count=0, is_silent=True),
            SourceFreshness("source_2", recent_count=5, is_silent=False),
        ]
        with self.assertRaisesMessage(CommandError, "Observability sources silent for 24h: source_1"):
            call_command("verify_observability_pipeline", "--strict")
