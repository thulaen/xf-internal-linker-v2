"""SimpleTestCase coverage for pure helpers extracted from tasks.py.

Each test class targets one extracted helper. No DB hits — the helpers
that touch a SessionCoOccurrenceRun receive an ``unittest.mock.Mock`` so
``run.save`` is a recorded call rather than a real write. The helpers
that read AppSetting (``_load_cooccurrence_window_settings`` and
``_is_hub_detection_enabled``) are tested via patched read functions.
"""

from __future__ import annotations

import types
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.cooccurrence.tasks import (
    _build_completed_alert_kwargs,
    _build_failure_alert_kwargs,
    _CooccurrenceWindowSettings,
    _finalize_completed_run,
    _finalize_failed_run,
    _is_hub_detection_enabled_value,
    _load_cooccurrence_window_settings,
    _mark_run_completed,
    _mark_run_failed,
    _score_suggestions_for_run,
)


# ---------------------------------------------------------------------------
# _load_cooccurrence_window_settings
# ---------------------------------------------------------------------------


class LoadCooccurrenceWindowSettingsTests(SimpleTestCase):
    def test_returns_dataclass_instance(self) -> None:
        with patch("apps.cooccurrence.tasks._read_int", return_value=42), patch(
            "apps.cooccurrence.tasks._read_float", return_value=0.5
        ):
            result = _load_cooccurrence_window_settings()
        self.assertIsInstance(result, _CooccurrenceWindowSettings)

    def test_routes_int_reads_to_two_int_fields(self) -> None:
        # Returns a fixed int for both _read_int calls (data_window_days,
        # min_co_session_count) and a fixed float for the float call.
        with patch("apps.cooccurrence.tasks._read_int", return_value=42), patch(
            "apps.cooccurrence.tasks._read_float", return_value=0.5
        ):
            result = _load_cooccurrence_window_settings()
        self.assertEqual(result.data_window_days, 42)
        self.assertEqual(result.min_co_session_count, 42)

    def test_routes_float_read_to_min_jaccard(self) -> None:
        with patch("apps.cooccurrence.tasks._read_int", return_value=42), patch(
            "apps.cooccurrence.tasks._read_float", return_value=0.123
        ):
            result = _load_cooccurrence_window_settings()
        self.assertAlmostEqual(result.min_jaccard, 0.123)

    def test_keys_are_correct_for_each_setting(self) -> None:
        # Verify each setting reads its OWN key, not just any key. Capture
        # the (key, default) calls and assert the exact triple.
        int_calls: list = []
        float_calls: list = []

        def fake_int(key: str, default: int) -> int:
            int_calls.append((key, default))
            return default

        def fake_float(key: str, default: float) -> float:
            float_calls.append((key, default))
            return default

        with patch("apps.cooccurrence.tasks._read_int", side_effect=fake_int), patch(
            "apps.cooccurrence.tasks._read_float", side_effect=fake_float
        ):
            _load_cooccurrence_window_settings()

        self.assertEqual(
            int_calls,
            [
                ("cooccurrence.data_window_days", 90),
                ("cooccurrence.min_co_session_count", 5),
            ],
        )
        self.assertEqual(float_calls, [("cooccurrence.min_jaccard", 0.05)])


# ---------------------------------------------------------------------------
# _mark_run_failed
# ---------------------------------------------------------------------------


class MarkRunFailedTests(SimpleTestCase):
    def test_sets_status_error_message_completed_at_and_saves(self) -> None:
        from apps.cooccurrence.models import SessionCoOccurrenceRun

        run = Mock()
        _mark_run_failed(run, "boom")
        self.assertEqual(run.status, SessionCoOccurrenceRun.STATUS_FAILED)
        self.assertEqual(run.error_message, "boom")
        self.assertIsNotNone(run.completed_at)
        run.save.assert_called_once()

    def test_save_is_called_with_targeted_update_fields(self) -> None:
        run = Mock()
        _mark_run_failed(run, "oops")
        kwargs = run.save.call_args.kwargs
        self.assertEqual(
            set(kwargs["update_fields"]),
            {"status", "error_message", "completed_at"},
        )


# ---------------------------------------------------------------------------
# _mark_run_completed
# ---------------------------------------------------------------------------


class MarkRunCompletedTests(SimpleTestCase):
    def test_sets_all_counter_fields(self) -> None:
        from apps.cooccurrence.models import SessionCoOccurrenceRun

        run = Mock()
        _mark_run_completed(run, sessions_processed=10, pairs_written=20, ga4_rows_fetched=30)
        self.assertEqual(run.status, SessionCoOccurrenceRun.STATUS_COMPLETED)
        self.assertEqual(run.sessions_processed, 10)
        self.assertEqual(run.pairs_written, 20)
        self.assertEqual(run.ga4_rows_fetched, 30)
        self.assertIsNotNone(run.completed_at)

    def test_save_is_called_with_full_update_fields(self) -> None:
        run = Mock()
        _mark_run_completed(run, 1, 2, 3)
        kwargs = run.save.call_args.kwargs
        self.assertEqual(
            set(kwargs["update_fields"]),
            {
                "status",
                "sessions_processed",
                "pairs_written",
                "ga4_rows_fetched",
                "completed_at",
            },
        )


# ---------------------------------------------------------------------------
# _build_failure_alert_kwargs
# ---------------------------------------------------------------------------


class BuildFailureAlertKwargsTests(SimpleTestCase):
    def test_returns_six_required_keys(self) -> None:
        kwargs = _build_failure_alert_kwargs("run-abc", RuntimeError("boom"))
        self.assertEqual(
            set(kwargs.keys()),
            {
                "event_type",
                "severity",
                "title",
                "message",
                "source_area",
                "dedupe_key",
            },
        )

    def test_event_type_and_severity_match_failure(self) -> None:
        kwargs = _build_failure_alert_kwargs("run-abc", RuntimeError("boom"))
        self.assertEqual(kwargs["event_type"], "cooccurrence.run_failed")
        self.assertEqual(kwargs["severity"], "error")

    def test_dedupe_key_includes_run_id(self) -> None:
        kwargs = _build_failure_alert_kwargs("run-xyz", RuntimeError("boom"))
        self.assertIn("run-xyz", kwargs["dedupe_key"])

    def test_message_includes_exception_text(self) -> None:
        kwargs = _build_failure_alert_kwargs("run-abc", RuntimeError("custom-text"))
        self.assertIn("custom-text", kwargs["message"])


# ---------------------------------------------------------------------------
# _build_completed_alert_kwargs
# ---------------------------------------------------------------------------


class BuildCompletedAlertKwargsTests(SimpleTestCase):
    def test_returns_six_required_keys(self) -> None:
        kwargs = _build_completed_alert_kwargs("run-abc", 100, 200)
        self.assertEqual(
            set(kwargs.keys()),
            {
                "event_type",
                "severity",
                "title",
                "message",
                "source_area",
                "dedupe_key",
            },
        )

    def test_event_type_and_severity_match_success(self) -> None:
        kwargs = _build_completed_alert_kwargs("run-abc", 100, 200)
        self.assertEqual(kwargs["event_type"], "cooccurrence.run_completed")
        self.assertEqual(kwargs["severity"], "info")

    def test_message_includes_pair_and_session_counts(self) -> None:
        kwargs = _build_completed_alert_kwargs("run-abc", sessions_processed=42, pairs_written=99)
        self.assertIn("42", kwargs["message"])
        self.assertIn("99", kwargs["message"])

    def test_dedupe_key_includes_run_id(self) -> None:
        kwargs = _build_completed_alert_kwargs("run-xyz", 1, 2)
        self.assertIn("run-xyz", kwargs["dedupe_key"])


# ---------------------------------------------------------------------------
# _is_hub_detection_enabled_value
# ---------------------------------------------------------------------------


class IsHubDetectionEnabledValueTests(SimpleTestCase):
    def test_none_means_enabled(self) -> None:
        self.assertTrue(_is_hub_detection_enabled_value(None))

    def test_empty_string_means_enabled(self) -> None:
        # Falsy → "missing" → enabled (matches the original ``if not row``).
        self.assertTrue(_is_hub_detection_enabled_value(""))

    def test_lowercase_false_means_disabled(self) -> None:
        self.assertFalse(_is_hub_detection_enabled_value("false"))

    def test_uppercase_false_means_disabled(self) -> None:
        # Case-insensitive — operator may have typed it any way.
        self.assertFalse(_is_hub_detection_enabled_value("FALSE"))

    def test_mixed_case_false_means_disabled(self) -> None:
        self.assertFalse(_is_hub_detection_enabled_value("False"))

    def test_true_means_enabled(self) -> None:
        self.assertTrue(_is_hub_detection_enabled_value("true"))

    def test_arbitrary_other_value_means_enabled(self) -> None:
        # Opt-out semantics: only the literal "false" disables.
        self.assertTrue(_is_hub_detection_enabled_value("yes"))
        self.assertTrue(_is_hub_detection_enabled_value("on"))
        self.assertTrue(_is_hub_detection_enabled_value("1"))


# ---------------------------------------------------------------------------
# _score_suggestions_for_run
# ---------------------------------------------------------------------------


class ScoreSuggestionsForRunTests(SimpleTestCase):
    def test_empty_list_returns_empty_list(self) -> None:
        with patch(
            "apps.cooccurrence.services.compute_value_model_score"
        ) as mock_score:
            result = _score_suggestions_for_run([], settings={}, site_max_jaccard=0.5)
        self.assertEqual(result, [])
        mock_score.assert_not_called()

    def test_each_suggestion_gets_score_and_diagnostics_set_in_place(self) -> None:
        sug_a = types.SimpleNamespace(score_value_model=None, value_model_diagnostics=None)
        sug_b = types.SimpleNamespace(score_value_model=None, value_model_diagnostics=None)
        with patch(
            "apps.cooccurrence.services.compute_value_model_score",
            return_value=(0.7, {"diag": True}),
        ):
            result = _score_suggestions_for_run(
                [sug_a, sug_b], settings={"enabled": True}, site_max_jaccard=0.5
            )
        self.assertEqual(sug_a.score_value_model, 0.7)
        self.assertEqual(sug_a.value_model_diagnostics, {"diag": True})
        self.assertEqual(sug_b.score_value_model, 0.7)
        self.assertEqual(sug_b.value_model_diagnostics, {"diag": True})
        self.assertIs(result[0], sug_a)
        self.assertIs(result[1], sug_b)

    def test_returns_same_list_reference_for_bulk_update(self) -> None:
        suggestions = [
            types.SimpleNamespace(score_value_model=None, value_model_diagnostics=None)
        ]
        with patch(
            "apps.cooccurrence.services.compute_value_model_score",
            return_value=(0.5, {}),
        ):
            result = _score_suggestions_for_run(
                suggestions, settings={}, site_max_jaccard=0.5
            )
        self.assertIs(result, suggestions)

    def test_compute_value_model_score_called_with_right_kwargs(self) -> None:
        sug = types.SimpleNamespace(
            score_value_model=None, value_model_diagnostics=None
        )
        with patch(
            "apps.cooccurrence.services.compute_value_model_score",
            return_value=(0.0, {}),
        ) as mock_score:
            _score_suggestions_for_run(
                [sug], settings={"enabled": True}, site_max_jaccard=0.42
            )
        mock_score.assert_called_once_with(
            suggestion=sug,
            settings={"enabled": True},
            site_max_jaccard=0.42,
        )


# ---------------------------------------------------------------------------
# _CooccurrenceWindowSettings dataclass shape
# ---------------------------------------------------------------------------


class CooccurrenceWindowSettingsShapeTests(SimpleTestCase):
    def test_dataclass_is_frozen(self) -> None:
        s = _CooccurrenceWindowSettings(
            data_window_days=90, min_co_session_count=5, min_jaccard=0.05
        )
        with self.assertRaises(Exception):  # FrozenInstanceError
            s.data_window_days = 99  # type: ignore[misc]

    def test_dataclass_holds_three_fields(self) -> None:
        s = _CooccurrenceWindowSettings(
            data_window_days=10, min_co_session_count=2, min_jaccard=0.1
        )
        self.assertEqual(s.data_window_days, 10)
        self.assertEqual(s.min_co_session_count, 2)
        self.assertAlmostEqual(s.min_jaccard, 0.1)


# ---------------------------------------------------------------------------
# _finalize_completed_run
# ---------------------------------------------------------------------------


class FinalizeCompletedRunTests(SimpleTestCase):
    def _make_run(self) -> Mock:
        run = Mock()
        run.run_id = "run-test-123"
        return run

    def test_returns_completed_result_dict(self) -> None:
        run = self._make_run()
        with patch(
            "apps.notifications.services.emit_operator_alert"
        ), patch(
            "apps.cooccurrence.tasks._is_hub_detection_enabled", return_value=False
        ):
            result = _finalize_completed_run(run, 10, 20, 30)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["sessions_processed"], 10)
        self.assertEqual(result["pairs_written"], 20)
        self.assertEqual(result["ga4_rows_fetched"], 30)
        self.assertEqual(result["run_id"], "run-test-123")

    def test_emits_completion_alert(self) -> None:
        run = self._make_run()
        with patch(
            "apps.notifications.services.emit_operator_alert"
        ) as mock_alert, patch(
            "apps.cooccurrence.tasks._is_hub_detection_enabled", return_value=False
        ):
            _finalize_completed_run(run, 1, 2, 3)
        mock_alert.assert_called_once()
        kwargs = mock_alert.call_args.kwargs
        self.assertEqual(kwargs["event_type"], "cooccurrence.run_completed")

    def test_chains_hub_detection_when_enabled(self) -> None:
        run = self._make_run()
        with patch(
            "apps.notifications.services.emit_operator_alert"
        ), patch(
            "apps.cooccurrence.tasks._is_hub_detection_enabled", return_value=True
        ), patch(
            "apps.cooccurrence.tasks.detect_behavioral_hubs"
        ) as mock_detect:
            _finalize_completed_run(run, 1, 2, 3)
        mock_detect.delay.assert_called_once()

    def test_skips_hub_detection_when_disabled(self) -> None:
        run = self._make_run()
        with patch(
            "apps.notifications.services.emit_operator_alert"
        ), patch(
            "apps.cooccurrence.tasks._is_hub_detection_enabled", return_value=False
        ), patch(
            "apps.cooccurrence.tasks.detect_behavioral_hubs"
        ) as mock_detect:
            _finalize_completed_run(run, 1, 2, 3)
        mock_detect.delay.assert_not_called()

    def test_marks_run_completed(self) -> None:
        from apps.cooccurrence.models import SessionCoOccurrenceRun

        run = self._make_run()
        with patch(
            "apps.notifications.services.emit_operator_alert"
        ), patch(
            "apps.cooccurrence.tasks._is_hub_detection_enabled", return_value=False
        ):
            _finalize_completed_run(run, 5, 6, 7)
        self.assertEqual(run.status, SessionCoOccurrenceRun.STATUS_COMPLETED)
        self.assertEqual(run.pairs_written, 6)
        run.save.assert_called_once()


# ---------------------------------------------------------------------------
# _finalize_failed_run
# ---------------------------------------------------------------------------


class FinalizeFailedRunTests(SimpleTestCase):
    def _make_run(self) -> Mock:
        run = Mock()
        run.run_id = "run-fail-456"
        return run

    def test_returns_failed_result_dict(self) -> None:
        run = self._make_run()
        with patch("apps.notifications.services.emit_operator_alert"):
            result = _finalize_failed_run(run, RuntimeError("boom"))
        self.assertEqual(result["status"], "failed")
        self.assertIn("boom", result["error"])

    def test_emits_failure_alert(self) -> None:
        run = self._make_run()
        with patch(
            "apps.notifications.services.emit_operator_alert"
        ) as mock_alert:
            _finalize_failed_run(run, RuntimeError("boom"))
        mock_alert.assert_called_once()
        kwargs = mock_alert.call_args.kwargs
        self.assertEqual(kwargs["event_type"], "cooccurrence.run_failed")
        self.assertEqual(kwargs["severity"], "error")

    def test_marks_run_failed(self) -> None:
        from apps.cooccurrence.models import SessionCoOccurrenceRun

        run = self._make_run()
        with patch("apps.notifications.services.emit_operator_alert"):
            _finalize_failed_run(run, RuntimeError("boom"))
        self.assertEqual(run.status, SessionCoOccurrenceRun.STATUS_FAILED)
        self.assertEqual(run.error_message, "boom")
        run.save.assert_called_once()
