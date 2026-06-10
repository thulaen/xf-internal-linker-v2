"""Convention-named SimpleTestCase coverage for apps/auto_issues/tasks.py.

The mutation gate discovers ONLY this exact filename (``tests_tasks.py`` next
to ``tasks.py``).  Every task here closes a stale database connection before it
starts work, BUT only when it is not already inside an open transaction
(atomic block).  Calling ``connection.close()`` inside an atomic block detaches
the connection mid-transaction, so the guard ``if not connection.in_atomic_block``
must hold both ways.

CRITICAL — these tasks call NETWORK pickers (``sync_glitchtip_issues``,
Pyroscope / Loki / Tempo / SonarQube / ``gh run list`` shells, etc.).  Every
test below mocks the module-level ``connection`` AND aborts the body at its
FIRST post-guard statement (the lazily-imported picker), so NO real Redis /
Celery / Postgres / HTTP call ever runs.  Letting a real body run would wedge
the mutation gate for 20+ minutes because each mutant re-runs the body.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class _StopAfterGuard(Exception):
    """Sentinel raised right after the connection guard to abort the body."""


class GlitchtipPickerGuardTests(SimpleTestCase):
    """pick_daily_glitchtip_issues closes the connection outside an atomic block."""

    def _run(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.auto_issues import tasks

        conn = MagicMock()
        conn.in_atomic_block = in_atomic_block
        # The first post-guard statement imports + calls sync_glitchtip_issues
        # (a network call to the GlitchTip API). Make it raise so the body
        # aborts immediately and no HTTP / picker work runs.
        with patch.object(tasks, "connection", conn), patch(
            "apps.audit.tasks.sync_glitchtip_issues", side_effect=_StopAfterGuard
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.pick_daily_glitchtip_issues()
        return conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=True)
        conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=False)
        conn.close.assert_called_once()


class NetworkPickerGuardCoverageTests(SimpleTestCase):
    """Exercise the connection guard in every picker task, network-free.

    Each task is run with a mocked connection (in_atomic_block=False so the
    close fires) and its first lazily-imported picker mocked with
    ``side_effect=_StopAfterGuard`` so the body aborts at the guard boundary
    before any Pyroscope / Loki / Tempo / pg_stat / gh-shell call runs.
    """

    def _conn(self) -> MagicMock:
        c = MagicMock()
        c.in_atomic_block = False
        return c

    def _assert_guard_runs(self, task_name: str, picker_path: str) -> None:
        from apps.auto_issues import tasks

        conn = self._conn()
        with patch.object(tasks, "connection", conn), patch(
            picker_path, side_effect=_StopAfterGuard
        ):
            with self.assertRaises(_StopAfterGuard):
                getattr(tasks, task_name)()
        conn.close.assert_called_once()

    def test_pick_daily_pyroscope_regressions_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_daily_pyroscope_regressions",
            "apps.auto_issues.services.pyroscope_picker.pick_pyroscope_regressions",
        )

    def test_pick_daily_loki_findings_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_daily_loki_findings",
            "apps.auto_issues.services.loki_picker.pick_loki_findings",
        )

    def test_pick_daily_faro_findings_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_daily_faro_findings",
            "apps.auto_issues.services.faro_picker.pick_faro_findings",
        )

    def test_pick_daily_tempo_findings_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_daily_tempo_findings",
            "apps.auto_issues.services.tempo_picker.pick_tempo_findings",
        )

    def test_pgexporter_findings_refresh_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pgexporter_findings_refresh",
            "apps.auto_issues.services.pgexporter_picker.pick_pgexporter_findings",
        )

    def test_pick_mutation_survivors_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_mutation_survivors",
            "apps.auto_issues.services.mutation.pick_mutation_survivors",
        )

    def test_pick_fuzz_crashes_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_fuzz_crashes",
            "apps.auto_issues.services.fuzz.pick_fuzz_crashes",
        )

    def test_pick_lint_errors_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_lint_errors",
            "apps.auto_issues.services.lint_error.pick_lint_errors",
        )

    def test_pick_contract_drift_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_contract_drift",
            "apps.auto_issues.services.contract_drift.pick_contract_drift",
        )

    def test_pick_ci_failed_runs_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_ci_failed_runs",
            "apps.auto_issues.services.ci_failed_runs.pick_ci_failed_runs",
        )

    def test_pick_daily_slow_queries_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_daily_slow_queries",
            "apps.auto_issues.services.slow_query_picker.pick_slow_queries",
        )

    def test_pick_daily_internal_issues_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_daily_internal_issues",
            "apps.auto_issues.services.internal_picker.pick_internal_issues",
        )

    def test_run_retention_cleanup_guard_runs(self) -> None:
        self._assert_guard_runs(
            "run_retention_cleanup",
            "apps.auto_issues.services.retention_cleanup.run_retention_cleanup",
        )

    def test_pick_disk_pressure_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_disk_pressure",
            "apps.auto_issues.services.disk_pressure_picker.pick_disk_pressure",
        )

    def test_pick_slo_probes_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_slo_probes",
            "apps.auto_issues.services.slo_probe_picker.pick_slo_probes",
        )

    def test_pick_missed_runs_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_missed_runs",
            "apps.auto_issues.services.missed_runs_picker.pick_missed_runs",
        )

    def test_pick_deploy_check_findings_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_deploy_check_findings",
            "apps.auto_issues.services.deploy_check_picker.pick_deploy_check_findings",
        )

    def test_pick_output_quality_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_output_quality",
            "apps.auto_issues.services.output_quality_picker.pick_output_quality",
        )

    def test_pick_weekly_pip_audit_findings_guard_runs(self) -> None:
        self._assert_guard_runs(
            "pick_weekly_pip_audit_findings",
            "apps.auto_issues.services.pip_audit_picker.pick_pip_audit_findings",
        )

    def test_run_findbugs_scan_task_guard_runs(self) -> None:
        self._assert_guard_runs(
            "run_findbugs_scan_task",
            "apps.auto_issues.services.findbugs.run_findbugs_scan",
        )


class CloseStaleIssuesThresholdTests(SimpleTestCase):
    """close_stale_issues closes the connection then queries through the ORM.

    The first post-guard statement is auto_close_stale_threshold(); the second
    is the AutoIssue queryset. Patching the threshold helper to raise aborts the
    body before any real DB query runs, proving the guard fired network-free.
    """

    def _run(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.auto_issues import tasks

        conn = MagicMock()
        conn.in_atomic_block = in_atomic_block
        with patch.object(tasks, "connection", conn), patch(
            "apps.auto_issues.services.scoring.auto_close_stale_threshold",
            side_effect=_StopAfterGuard,
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.close_stale_issues()
        return conn

    def test_close_called_when_not_in_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=False)
        conn.close.assert_called_once()

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=True)
        conn.close.assert_not_called()
