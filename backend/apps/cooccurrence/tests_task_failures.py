"""Focused tests for co-occurrence task failure classification."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from googleapiclient.errors import HttpError

from apps.cooccurrence.models import SessionCoOccurrenceRun
from apps.cooccurrence.tasks import compute_session_cooccurrence


def _google_http_error() -> HttpError:
    response = SimpleNamespace(status=400, reason="Bad Request")
    return HttpError(response, b'{"error": {"message": "bad property"}}')


class CooccurrenceTaskFailureTests(TestCase):
    def test_google_http_error_is_failed_job_not_exception_log(self) -> None:
        with (
            patch(
                "apps.cooccurrence.services.fetch_ga4_session_cooccurrence",
                side_effect=_google_http_error(),
            ),
            patch("apps.cooccurrence.tasks.logger.exception") as exception_log,
            patch("apps.cooccurrence.tasks.logger.warning") as warning_log,
            patch("apps.notifications.services.emit_operator_alert"),
        ):
            result = compute_session_cooccurrence.run()

        run = SessionCoOccurrenceRun.objects.get()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(run.status, SessionCoOccurrenceRun.STATUS_FAILED)
        warning_log.assert_called_once()
        exception_log.assert_not_called()
