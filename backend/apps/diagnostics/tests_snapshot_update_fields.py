"""
Tests that _write_service_snapshot uses update_fields when saving
ServiceStatusSnapshot rows (RUSTBUG-PERF-008 fix).

Without update_fields, snapshot.save() rewrites all columns including
created_at, service_name, and last_success even when only state changes.

These tests assert the EXACT update_fields list (not just membership) and
exercise all three state branches (healthy / failed / neither) so the
diff-scoped mutation gate cannot keep a survivor on the changed lines:
the literal base list, the "healthy"/"failed" comparison strings, the
"==" operators, and the appended "last_success"/"last_failure" columns.

AutoIssue: #2162
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


def _call_write(state: str):
    """Invoke _write_service_snapshot with a mocked snapshot and return it."""
    from apps.diagnostics.health import _write_service_snapshot  # noqa: PLC0415

    mock_snapshot = MagicMock()
    checked_at = MagicMock()
    with patch(
        "apps.diagnostics.health.ServiceStatusSnapshot.objects.get_or_create",
        return_value=(mock_snapshot, False),
    ):
        _write_service_snapshot(
            service="redis",
            state=state,
            explanation="OK",
            next_step="monitor",
            metadata={"k": "v"},
            checked_at=checked_at,
        )
    return mock_snapshot, checked_at


class SnapshotSaveUpdateFieldsTests(SimpleTestCase):
    """snapshot.save() must specify the exact update_fields list per branch."""

    def test_assigned_columns_are_set_on_the_snapshot(self):
        """The four always-written columns must be assigned the passed values."""
        mock_snapshot, _ = _call_write("healthy")
        self.assertEqual(mock_snapshot.state, "healthy")
        self.assertEqual(mock_snapshot.explanation, "OK")
        self.assertEqual(mock_snapshot.next_action_step, "monitor")
        self.assertEqual(mock_snapshot.metadata, {"k": "v"})

    def test_save_called_exactly_once_with_update_fields_kwarg(self):
        mock_snapshot, _ = _call_write("degraded")
        self.assertEqual(mock_snapshot.save.call_count, 1)
        kwargs = mock_snapshot.save.call_args[1]
        self.assertIn("update_fields", kwargs)
        self.assertEqual(mock_snapshot.save.call_args[0], ())

    def test_healthy_update_fields_exact_list(self):
        """state == 'healthy' appends ONLY last_success, in this exact order."""
        mock_snapshot, checked_at = _call_write("healthy")
        uf = mock_snapshot.save.call_args[1]["update_fields"]
        self.assertEqual(
            uf,
            [
                "state",
                "explanation",
                "next_action_step",
                "metadata",
                "updated_at",
                "last_success",
            ],
        )
        self.assertEqual(mock_snapshot.last_success, checked_at)

    def test_failed_update_fields_exact_list(self):
        """state == 'failed' appends ONLY last_failure, in this exact order."""
        mock_snapshot, checked_at = _call_write("failed")
        uf = mock_snapshot.save.call_args[1]["update_fields"]
        self.assertEqual(
            uf,
            [
                "state",
                "explanation",
                "next_action_step",
                "metadata",
                "updated_at",
                "last_failure",
            ],
        )
        self.assertEqual(mock_snapshot.last_failure, checked_at)

    def test_neither_branch_update_fields_exact_base_list(self):
        """A state that is neither 'healthy' nor 'failed' appends nothing.

        This pins the base list literal and proves both the '== healthy' and
        '== failed' comparisons are false here — flipping either operator to
        '!=' would change this list and fail the test.
        """
        mock_snapshot, _ = _call_write("degraded")
        uf = mock_snapshot.save.call_args[1]["update_fields"]
        self.assertEqual(
            uf,
            ["state", "explanation", "next_action_step", "metadata", "updated_at"],
        )

    def test_healthy_does_not_touch_last_failure_column(self):
        mock_snapshot, _ = _call_write("healthy")
        uf = mock_snapshot.save.call_args[1]["update_fields"]
        self.assertNotIn("last_failure", uf)

    def test_failed_does_not_touch_last_success_column(self):
        mock_snapshot, _ = _call_write("failed")
        uf = mock_snapshot.save.call_args[1]["update_fields"]
        self.assertNotIn("last_success", uf)
