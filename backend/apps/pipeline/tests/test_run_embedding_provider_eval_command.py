"""Tests for the provider score management command."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class RunEmbeddingProviderEvalCommandTests(SimpleTestCase):
    def test_when_cost_not_confirmed_then_command_errors(self) -> None:
        with self.assertRaises(CommandError):
            call_command("run_embedding_provider_eval")

    def test_when_cost_confirmed_then_task_starts(self) -> None:
        out = StringIO()
        with patch(
            "apps.pipeline.management.commands.run_embedding_provider_eval."
            "embedding_provider_bakeoff.delay",
            return_value=SimpleNamespace(id="task-1"),
        ) as delay:
            call_command(
                "run_embedding_provider_eval",
                "--sample-size",
                "25",
                "--confirm-cost",
                stdout=out,
            )
        delay.assert_called_once_with(sample_size=25)
        self.assertIn("task-1", out.getvalue())

    def test_when_dry_run_then_task_does_not_start(self) -> None:
        out = StringIO()
        with patch(
            "apps.pipeline.management.commands.run_embedding_provider_eval."
            "embedding_provider_bakeoff.delay",
        ) as delay:
            call_command(
                "run_embedding_provider_eval",
                "--sample-size",
                "25",
                "--dry-run",
                stdout=out,
            )

        delay.assert_not_called()
        self.assertIn("Dry run only", out.getvalue())
