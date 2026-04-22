"""Model-level tests for the Scheduled Updates orchestrator (PR-B.1).

Covers only the behaviours the models themselves enforce:

- ``JobAlert`` dedup via ``UNIQUE(job_key, alert_type, calendar_date)``.
- ``ScheduledJob.log_tail`` truncation.
- ``JobAlert.is_active`` property transitions.

Runner / window-guard / catch-up / channels tests land in subsequent
PR-B slices (B.2, B.3, B.4) alongside their implementations.
"""

from __future__ import annotations

import datetime as dt

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import (
    ALERT_TYPE_MISSED,
    JOB_PRIORITY_HIGH,
    JOB_STATE_RUNNING,
    JobAlert,
    ScheduledJob,
)


class ScheduledJobLogTailTests(TestCase):
    def test_log_tail_truncates_past_max_chars(self) -> None:
        job = ScheduledJob.objects.create(
            key="demo-job",
            display_name="Demo job",
            priority=JOB_PRIORITY_HIGH,
            log_tail="x" * (ScheduledJob.LOG_TAIL_MAX_CHARS + 500),
        )

        # Tail must stay within limit, truncation marker present.
        assert len(job.log_tail) <= ScheduledJob.LOG_TAIL_MAX_CHARS
        assert job.log_tail.startswith("...[truncated")

    def test_log_tail_under_max_is_preserved_verbatim(self) -> None:
        text = "every line preserved\n" * 10
        job = ScheduledJob.objects.create(
            key="small-log-job",
            display_name="Small log",
            log_tail=text,
        )

        assert job.log_tail == text

    def test_state_default_is_pending(self) -> None:
        job = ScheduledJob.objects.create(key="k", display_name="K")
        assert job.state == "pending"
        assert job.pause_token is False
        assert job.progress_pct == 0.0


class JobAlertDedupTests(TestCase):
    def test_unique_per_job_day_type(self) -> None:
        today = dt.date.today()
        JobAlert.objects.create(
            job_key="pagerank_refresh",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=today,
            message="Missed the 14:30 window",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # Second row with the same (job, type, date) MUST fail.
                JobAlert.objects.create(
                    job_key="pagerank_refresh",
                    alert_type=ALERT_TYPE_MISSED,
                    calendar_date=today,
                    message="duplicate — should be rejected",
                )

    def test_update_or_create_collapses_duplicates(self) -> None:
        """Runner code uses update_or_create — exercise that path."""
        today = dt.date.today()

        first, created_first = JobAlert.objects.update_or_create(
            job_key="lda_topic_refresh",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=today,
            defaults={"message": "initial"},
        )
        assert created_first is True

        second, created_second = JobAlert.objects.update_or_create(
            job_key="lda_topic_refresh",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=today,
            defaults={"message": "seen again"},
        )
        assert created_second is False
        assert second.pk == first.pk
        assert second.message == "seen again"

        # Exactly one row after two update_or_creates.
        assert (
            JobAlert.objects.filter(
                job_key="lda_topic_refresh",
                alert_type=ALERT_TYPE_MISSED,
                calendar_date=today,
            ).count()
            == 1
        )

    def test_is_active_transitions(self) -> None:
        alert = JobAlert.objects.create(
            job_key="bloom_filter_ids_rebuild",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=dt.date.today(),
        )
        assert alert.is_active is True

        alert.acknowledged_at = dt.datetime(2026, 4, 22, 12, 0, tzinfo=dt.timezone.utc)
        assert alert.is_active is False

        alert.acknowledged_at = None
        alert.resolved_at = dt.datetime(2026, 4, 22, 13, 0, tzinfo=dt.timezone.utc)
        assert alert.is_active is False


class ScheduledJobCreationSmokeTest(TestCase):
    def test_round_trip(self) -> None:
        job = ScheduledJob.objects.create(
            key="trustrank_auto_seeder",
            display_name="TrustRank Auto-Seeder",
            priority=JOB_PRIORITY_HIGH,
            state=JOB_STATE_RUNNING,
            progress_pct=42.5,
            cadence_seconds=86400,
            duration_estimate_sec=120,
            current_message="Computing inverse PageRank…",
        )
        refetched = ScheduledJob.objects.get(pk=job.pk)
        assert refetched.display_name == "TrustRank Auto-Seeder"
        assert refetched.current_message == "Computing inverse PageRank…"
        assert str(refetched) == "trustrank_auto_seeder [running]"
