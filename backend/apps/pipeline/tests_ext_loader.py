"""Unit tests for the C++ extension loader's failure-logging helper.

``_log_to_errorlog`` writes a missing/broken C++ extension to BOTH the
ErrorLog table (operator-facing /error-log page) AND an AutoIssue row
(picked up at the next session start). Both writes are best-effort: if
either surface is unavailable — e.g. during early startup, in a test
harness without the table, or because the AutoIssue dedup service raised —
the helper must swallow the failure and log it at DEBUG level rather than
letting it bubble up to the pipeline orchestrator.

These tests pin that swallow-and-log behaviour for the two ``except``
blocks so a future refactor cannot quietly turn a best-effort write back
into a crash.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.pipeline.services import ext_loader


class LogToErrorLogTests(SimpleTestCase):
    def test_errorlog_write_failure_is_swallowed_and_logged_at_debug(self):
        # ErrorLog.objects.create blows up (table missing / early startup).
        # The helper must NOT raise; it must emit a DEBUG log line and then
        # carry on to the AutoIssue surface.
        fake_errorlog = mock.Mock()
        fake_errorlog.objects.create.side_effect = RuntimeError("no ErrorLog table")

        with (
            mock.patch.dict(
                "sys.modules",
                {"apps.audit.models": mock.Mock(ErrorLog=fake_errorlog)},
            ),
            mock.patch.object(ext_loader, "logger") as fake_logger,
            mock.patch(
                "apps.auto_issues.services.dedup.upsert_dedup"
            ),
        ):
            # Must return None (no raise) even though ErrorLog failed.
            self.assertIsNone(
                ext_loader._log_to_errorlog(
                    "scoring", "import", "boom", RuntimeError("orig")
                )
            )

        # The ErrorLog except branch logged a DEBUG line about the failure.
        debug_messages = [c.args[0] for c in fake_logger.debug.call_args_list]
        self.assertIn(
            "Could not write C++ extension failure to ErrorLog", debug_messages
        )

    def test_autoissue_write_failure_is_swallowed_and_logged_at_debug(self):
        # The ErrorLog write succeeds, but the AutoIssue dedup service raises.
        # The helper must swallow it and log a DEBUG line for the AutoIssue
        # surface — never propagate to the caller.
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

    def test_happy_path_writes_both_surfaces(self):
        # When both surfaces are healthy, the helper writes an ErrorLog row
        # and an AutoIssue observation. This is the positive control that the
        # changed except-bindings did not change the success behaviour.
        fake_errorlog = mock.Mock()

        with (
            mock.patch.dict(
                "sys.modules",
                {"apps.audit.models": mock.Mock(ErrorLog=fake_errorlog)},
            ),
            mock.patch(
                "apps.auto_issues.services.dedup.upsert_dedup"
            ) as upsert,
        ):
            ext_loader._log_to_errorlog(
                "phrase_match", "import", "failed to import", ImportError("x")
            )

        fake_errorlog.objects.create.assert_called_once()
        create_kwargs = fake_errorlog.objects.create.call_args.kwargs
        self.assertEqual(create_kwargs["job_type"], "cpp_extension")
        self.assertEqual(create_kwargs["step"], "import_phrase_match")
        upsert.assert_called_once()
