"""Tests for the alerts module (PR-B.3).

Covers the four behaviours operators care about:

1. ``raise_alert`` upserts — never two rows per (job, day, type).
2. A reopened-after-resolve alert surfaces again (badge re-counts it).
3. Successful completion auto-resolves all of the job's open alerts.
4. ``detect_missed_jobs`` transitions stale jobs + raises exactly one
   MISSED alert per calendar day, even when called repeatedly.

Also verifies ``prune_resolved_alerts`` retention and
``detect_stalled_jobs`` alert raising.
"""

from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.utils import timezone

from .alerts import (
    RESOLVED_ALERT_RETENTION_DAYS,
    STALLED_JOB_THRESHOLD_SECONDS,
    acknowledge,
    active_alerts_count,
    detect_missed_jobs,
    detect_stalled_jobs,
    prune_resolved_alerts,
    raise_alert,
    resolve_open_alerts_for_job,
)
from .models import (
    ALERT_TYPE_FAILED,
    ALERT_TYPE_MISSED,
    ALERT_TYPE_STALLED,
    JOB_STATE_COMPLETED,
    JOB_STATE_MISSED,
    JOB_STATE_RUNNING,
    JobAlert,
    ScheduledJob,
)


TODAY = dt.date(2026, 4, 22)
EARLIER_TODAY = dt.datetime(2026, 4, 22, 10, 0, tzinfo=dt.timezone.utc)
NOW = dt.datetime(2026, 4, 22, 15, 0, tzinfo=dt.timezone.utc)


# ─────────────────────────────────────────────────────────────────────
# raise_alert / resolve / acknowledge
# ─────────────────────────────────────────────────────────────────────


class RaiseAlertTests(TestCase):
    def test_first_call_creates_row(self) -> None:
        alert, created = raise_alert(
            job_key="pagerank_refresh",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
            message="first raise",
        )
        assert created is True
        assert alert.message == "first raise"
        assert alert.resolved_at is None

    def test_second_same_day_updates_message_and_keeps_single_row(self) -> None:
        raise_alert(
            job_key="lda_topic_refresh",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
            message="first",
        )
        alert, created = raise_alert(
            job_key="lda_topic_refresh",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
            message="retrigger — more info",
        )
        assert created is False
        assert alert.message == "retrigger — more info"
        assert (
            JobAlert.objects.filter(
                job_key="lda_topic_refresh",
                alert_type=ALERT_TYPE_MISSED,
                calendar_date=TODAY,
            ).count()
            == 1
        )

    def test_raise_reopens_resolved_alert(self) -> None:
        alert, _ = raise_alert(
            job_key="kenlm_retrain",
            alert_type=ALERT_TYPE_FAILED,
            calendar_date=TODAY,
            message="first fail",
        )
        alert.resolved_at = timezone.now()
        alert.save(update_fields=["resolved_at"])

        _, created_again = raise_alert(
            job_key="kenlm_retrain",
            alert_type=ALERT_TYPE_FAILED,
            calendar_date=TODAY,
            message="fails again after a clean run",
        )
        assert created_again is False
        refetched = JobAlert.objects.get(pk=alert.pk)
        assert refetched.resolved_at is None, "reopened alert must be active again"


class ResolveOpenAlertsTests(TestCase):
    def test_only_touches_unresolved_rows(self) -> None:
        # One open, one previously resolved for the same job.
        raise_alert(
            job_key="node2vec_walks",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
        )
        old = JobAlert.objects.create(
            job_key="node2vec_walks",
            alert_type=ALERT_TYPE_FAILED,
            calendar_date=TODAY - dt.timedelta(days=3),
            resolved_at=NOW - dt.timedelta(days=2),
        )

        count = resolve_open_alerts_for_job("node2vec_walks", now=NOW)
        assert count == 1

        old.refresh_from_db()
        # Pre-resolved row is untouched.
        assert old.resolved_at == NOW - dt.timedelta(days=2)

    def test_resolves_acknowledged_too(self) -> None:
        alert, _ = raise_alert(
            job_key="collocations_pmi_rebuild",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
        )
        alert.acknowledged_at = NOW - dt.timedelta(hours=3)
        alert.save(update_fields=["acknowledged_at"])

        count = resolve_open_alerts_for_job("collocations_pmi_rebuild", now=NOW)
        assert count == 1

        alert.refresh_from_db()
        assert alert.resolved_at is not None
        assert alert.acknowledged_at is not None  # history preserved


class AcknowledgeTests(TestCase):
    def test_sets_timestamp_and_hides_from_active(self) -> None:
        alert, _ = raise_alert(
            job_key="weight_tuner_lbfgs_tpe",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
        )
        assert active_alerts_count() == 1

        acknowledge(alert.pk, now=NOW)
        alert.refresh_from_db()

        assert alert.acknowledged_at == NOW
        assert alert.is_active is False
        assert active_alerts_count() == 0

    def test_unknown_id_returns_none(self) -> None:
        assert acknowledge(999_999) is None


# ─────────────────────────────────────────────────────────────────────
# detect_missed_jobs
# ─────────────────────────────────────────────────────────────────────


class DetectMissedJobsTests(TestCase):
    def _job(
        self,
        key: str,
        *,
        state: str = JOB_STATE_COMPLETED,
        cadence_seconds: int = 86400,
        last_success_at: dt.datetime | None = None,
        created_at: dt.datetime | None = None,
    ) -> ScheduledJob:
        job = ScheduledJob.objects.create(
            key=key,
            display_name=key.replace("_", " ").title(),
            state=state,
            cadence_seconds=cadence_seconds,
            last_success_at=last_success_at,
        )
        if created_at is not None:
            # TimestampedModel.created_at is auto_now_add — patch via update.
            ScheduledJob.objects.filter(pk=job.pk).update(created_at=created_at)
            job.refresh_from_db()
        return job

    def test_transitions_stale_to_missed(self) -> None:
        # Cadence 1 day, last success 3 days ago → stale (slack=1.5 days).
        stale = self._job(
            "stale-1",
            last_success_at=NOW - dt.timedelta(days=3),
        )
        fresh = self._job(
            "fresh-1",
            last_success_at=NOW - dt.timedelta(hours=6),
        )
        transitioned = detect_missed_jobs(now=NOW)

        stale.refresh_from_db()
        fresh.refresh_from_db()

        assert stale.state == JOB_STATE_MISSED
        assert fresh.state == JOB_STATE_COMPLETED
        assert {j.pk for j in transitioned} == {stale.pk}

    def test_raises_exactly_one_alert_per_day_across_repeated_calls(self) -> None:
        self._job(
            "stale-2",
            last_success_at=NOW - dt.timedelta(days=3),
        )
        for _ in range(5):
            detect_missed_jobs(now=NOW)

        alerts = JobAlert.objects.filter(
            job_key="stale-2",
            alert_type=ALERT_TYPE_MISSED,
        )
        assert alerts.count() == 1

    def test_zero_cadence_never_flagged(self) -> None:
        # cadence_seconds=0 means "on-demand only" — never missed.
        self._job(
            "on-demand",
            cadence_seconds=0,
            last_success_at=None,
            created_at=NOW - dt.timedelta(days=365),
        )
        transitioned = detect_missed_jobs(now=NOW)
        assert transitioned == []
        assert JobAlert.objects.filter(job_key="on-demand").count() == 0

    def test_running_jobs_not_flagged(self) -> None:
        # A job currently executing is not "stale" even with an old
        # last_success_at — the in-flight run counts.
        self._job(
            "in-flight",
            state=JOB_STATE_RUNNING,
            last_success_at=NOW - dt.timedelta(days=30),
        )
        transitioned = detect_missed_jobs(now=NOW)
        assert [j.key for j in transitioned] == []


class DetectStalledJobsTests(TestCase):
    def test_raises_stalled_alert_without_flipping_state(self) -> None:
        # Running longer than 4 h → alert fires.
        running = ScheduledJob.objects.create(
            key="long-runner",
            display_name="Long Runner",
            state=JOB_STATE_RUNNING,
            started_at=NOW
            - dt.timedelta(hours=STALLED_JOB_THRESHOLD_SECONDS // 3600 + 1),
        )
        detected = detect_stalled_jobs(now=NOW)

        assert [j.pk for j in detected] == [running.pk]
        assert (
            JobAlert.objects.filter(
                job_key="long-runner",
                alert_type=ALERT_TYPE_STALLED,
            ).count()
            == 1
        )

        running.refresh_from_db()
        # State is NOT changed — operator decides whether to pause/cancel.
        assert running.state == JOB_STATE_RUNNING


# ─────────────────────────────────────────────────────────────────────
# prune_resolved_alerts
# ─────────────────────────────────────────────────────────────────────


class PruneResolvedAlertsTests(TestCase):
    def test_deletes_only_old_resolved_rows(self) -> None:
        recent = JobAlert.objects.create(
            job_key="recent",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
            resolved_at=NOW - dt.timedelta(days=1),
        )
        old = JobAlert.objects.create(
            job_key="old",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY - dt.timedelta(days=100),
            resolved_at=NOW - dt.timedelta(days=RESOLVED_ALERT_RETENTION_DAYS + 5),
        )
        active = JobAlert.objects.create(
            job_key="active",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
        )

        deleted = prune_resolved_alerts(now=NOW)
        assert deleted == 1
        assert JobAlert.objects.filter(pk=recent.pk).exists()
        assert not JobAlert.objects.filter(pk=old.pk).exists()
        assert JobAlert.objects.filter(pk=active.pk).exists()


# ─────────────────────────────────────────────────────────────────────
# Runner integration (COMPLETED auto-resolve, FAILED raises)
# ─────────────────────────────────────────────────────────────────────


class RunnerAlertIntegrationTests(TestCase):
    """Exercise runner._execute_job with the alert wiring in place."""

    def tearDown(self) -> None:
        # Clean registry to keep tests independent.
        from .registry import JOB_REGISTRY

        JOB_REGISTRY.pop("alerts-success", None)
        JOB_REGISTRY.pop("alerts-fail", None)

    def test_successful_run_auto_resolves_open_alerts(self) -> None:
        from .registry import scheduled_job
        from .runner import _execute_job, JOB_REGISTRY

        @scheduled_job(
            "alerts-success",
            display_name="alerts success",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            checkpoint(progress_pct=50)

        job = ScheduledJob.objects.create(
            key="alerts-success",
            display_name="alerts success",
            cadence_seconds=86400,
        )
        # Pre-existing open alert from a previous missed run.
        raise_alert(
            job_key="alerts-success",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
        )
        assert active_alerts_count() == 1

        _execute_job(job, JOB_REGISTRY["alerts-success"])

        job.refresh_from_db()
        assert job.state == JOB_STATE_COMPLETED
        assert active_alerts_count() == 0

    def test_failed_run_raises_alert(self) -> None:
        from .registry import scheduled_job
        from .runner import _execute_job, JOB_REGISTRY

        @scheduled_job(
            "alerts-fail",
            display_name="alerts fail",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            raise RuntimeError("boom in test")

        job = ScheduledJob.objects.create(
            key="alerts-fail",
            display_name="alerts fail",
        )
        _execute_job(job, JOB_REGISTRY["alerts-fail"])

        alerts = JobAlert.objects.filter(
            job_key="alerts-fail",
            alert_type=ALERT_TYPE_FAILED,
        )
        assert alerts.count() == 1
        alert = alerts.first()
        assert alert is not None
        assert "boom in test" in alert.message
