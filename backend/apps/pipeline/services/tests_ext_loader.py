"""Co-located focused coverage tests for ``ext_loader._log_to_errorlog``.

The two ``except`` branches in ``_log_to_errorlog`` (the ErrorLog write and
the AutoIssue write) are best-effort: each must swallow its failure and log a
DEBUG line instead of letting the exception reach the pipeline orchestrator.

These tests pin those two branches directly. They live next to
``ext_loader.py`` (same ``services/`` dir, stem ``tests_ext_loader``) so a
per-file coverage run resolving ``services/ext_loader.py`` ->
``services/tests_ext_loader.py`` still executes both failure paths.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.pipeline.services import ext_loader


class LogToErrorLogBranchTests(SimpleTestCase):
    def test_errorlog_write_failure_swallowed_and_debug_logged(self) -> None:
        # ErrorLog.objects.create raises (table missing during early startup).
        # The except branch (lines ~111/113) must log at DEBUG and continue;
        # it must NOT raise. AutoIssue write is stubbed so it stays green.
        fake_errorlog = mock.Mock()
        fake_errorlog.objects.create.side_effect = RuntimeError("no ErrorLog table")

        with (
            mock.patch.dict(
                "sys.modules",
                {"apps.audit.models": mock.Mock(ErrorLog=fake_errorlog)},
            ),
            mock.patch.object(ext_loader, "logger") as fake_logger,
            mock.patch("apps.auto_issues.services.dedup.upsert_dedup"),
        ):
            self.assertIsNone(
                ext_loader._log_to_errorlog(
                    "scoring", "import", "boom", RuntimeError("orig")
                )
            )

        debug_messages = [c.args[0] for c in fake_logger.debug.call_args_list]
        self.assertIn(
            "Could not write C++ extension failure to ErrorLog", debug_messages
        )

    def test_autoissue_write_failure_swallowed_and_debug_logged(self) -> None:
        # ErrorLog write succeeds, but the AutoIssue dedup service raises.
        # The second except branch (lines ~144/145) must log at DEBUG and
        # return None without propagating the error.
        fake_errorlog = mock.Mock()

        with (
            mock.patch.dict(
                "sys.modules",
                {"apps.audit.models": mock.Mock(ErrorLog=fake_errorlog)},
            ),
            mock.patch.object(ext_loader, "logger") as fake_logger,
            mock.patch(
                "apps.auto_issues.services.dedup.upsert_dedup",
                side_effect=RuntimeError("dedup index offline"),
            ),
        ):
            self.assertIsNone(
                ext_loader._log_to_errorlog("simsearch", "missing_attr", "gone")
            )

        debug_messages = [c.args[0] for c in fake_logger.debug.call_args_list]
        self.assertIn(
            "Could not write C++ extension failure to AutoIssue", debug_messages
        )
