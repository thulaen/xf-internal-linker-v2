"""Tests for broadcast wiring (PR-B.4).

Every broadcast goes through ``apps.realtime.services.broadcast`` which
silently no-ops without Redis. Under test, we patch that helper and
assert:

- the ``scheduled_updates`` topic is used
- the right event name fires at the right lifecycle point
- the payload carries the fields the UI will render

No real channel layer is needed — the assertions are on the helper call
itself.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

from django.test import TestCase

from .alerts import (
    acknowledge,
    raise_alert,
    resolve_open_alerts_for_job,
)
from .broadcasts import (
    TOPIC_SCHEDULED_UPDATES,
    _job_summary,
    broadcast_alert_acknowledged,
    broadcast_alert_raised,
    broadcast_alerts_resolved,
    broadcast_progress,
    broadcast_state_change,
)
from .models import (
    ALERT_TYPE_FAILED,
    ALERT_TYPE_MISSED,
    JOB_PRIORITY_HIGH,
    JOB_STATE_COMPLETED,
    JOB_STATE_PAUSED,
    JOB_STATE_RUNNING,
    JobAlert,
    ScheduledJob,
)
from .registry import JOB_REGISTRY, scheduled_job, unregister_for_test
from .runner import _execute_job

BROADCAST_TARGET = "apps.scheduled_updates.broadcasts.broadcast"

TODAY = dt.date(2026, 4, 22)


# ─────────────────────────────────────────────────────────────────────
# Direct broadcast helpers
# ─────────────────────────────────────────────────────────────────────


class BroadcastHelperTests(TestCase):
    def test_job_summary_includes_expected_fields(self) -> None:
        job = ScheduledJob.objects.create(
            key="demo",
            display_name="Demo",
            priority=JOB_PRIORITY_HIGH,
            state=JOB_STATE_RUNNING,
            progress_pct=42.0,
            current_message="Halfway",
        )
        summary = _job_summary(job)
        for field in (
            "key",
            "display_name",
            "state",
            "priority",
            "progress_pct",
            "current_message",
            "started_at",
            "finished_at",
            "last_run_at",
            "last_success_at",
            "cadence_seconds",
            "duration_estimate_sec",
            "pause_token",
        ):
            assert field in summary, f"missing field {field}"

    @patch(BROADCAST_TARGET)
    def test_broadcast_progress_fires_job_progress_event(self, mock_bcast):
        broadcast_progress("pagerank_refresh", 55.5, "Iteration 12 of 50")

        mock_bcast.assert_called_once()
        kwargs = mock_bcast.call_args.kwargs
        assert kwargs["topic"] == TOPIC_SCHEDULED_UPDATES
        assert kwargs["event"] == "job.progress"
        assert kwargs["payload"]["key"] == "pagerank_refresh"
        assert kwargs["payload"]["progress_pct"] == 55.5
        assert kwargs["payload"]["current_message"] == "Iteration 12 of 50"

    @patch(BROADCAST_TARGET)
    def test_broadcast_state_change_fires_job_state_change_event(self, mock_bcast):
        job = ScheduledJob.objects.create(
            key="demo-state",
            display_name="Demo state",
            state=JOB_STATE_COMPLETED,
        )
        broadcast_state_change(job)

        mock_bcast.assert_called_once()
        kwargs = mock_bcast.call_args.kwargs
        assert kwargs["topic"] == TOPIC_SCHEDULED_UPDATES
        assert kwargs["event"] == "job.state_change"
        assert kwargs["payload"]["key"] == "demo-state"
        assert kwargs["payload"]["state"] == JOB_STATE_COMPLETED

    @patch(BROADCAST_TARGET)
    def test_broadcast_alert_raised_carries_reopened_flag(self, mock_bcast):
        alert = JobAlert.objects.create(
            job_key="kenlm_retrain",
            alert_type=ALERT_TYPE_FAILED,
            calendar_date=TODAY,
            message="boom",
        )
        broadcast_alert_raised(alert, reopened=True)

        kwargs = mock_bcast.call_args.kwargs
        assert kwargs["event"] == "alert.raised"
        assert kwargs["payload"]["id"] == alert.pk
        assert kwargs["payload"]["job_key"] == "kenlm_retrain"
        assert kwargs["payload"]["reopened"] is True

    @patch(BROADCAST_TARGET)
    def test_broadcast_alerts_resolved_emits_count(self, mock_bcast):
        broadcast_alerts_resolved("node2vec_walks", 3)
        kwargs = mock_bcast.call_args.kwargs
        assert kwargs["event"] == "alert.resolved"
        assert kwargs["payload"] == {"job_key": "node2vec_walks", "count": 3}

    @patch(BROADCAST_TARGET)
    def test_broadcast_alert_acknowledged(self, mock_bcast):
        alert = JobAlert.objects.create(
            job_key="trustrank_propagation",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
        )
        broadcast_alert_acknowledged(alert)
        kwargs = mock_bcast.call_args.kwargs
        assert kwargs["event"] == "alert.acknowledged"
        assert kwargs["payload"]["id"] == alert.pk


# ─────────────────────────────────────────────────────────────────────
# Runner integration — verify broadcasts fire at each lifecycle step
# ─────────────────────────────────────────────────────────────────────


class RunnerBroadcastWiringTests(TestCase):
    def tearDown(self) -> None:
        for key in ("bcast-success", "bcast-fail", "bcast-pause", "bcast-progress"):
            unregister_for_test(key)

    @patch(BROADCAST_TARGET)
    def test_completed_run_fires_expected_sequence(self, mock_bcast):
        @scheduled_job(
            "bcast-success",
            display_name="bcast success",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            checkpoint(progress_pct=30.0, message="third done")
            checkpoint(progress_pct=75.0, message="almost there")

        job = ScheduledJob.objects.create(
            key="bcast-success",
            display_name="bcast success",
        )
        _execute_job(job, JOB_REGISTRY["bcast-success"])

        events = [c.kwargs["event"] for c in mock_bcast.call_args_list]
        # Sequence: RUNNING state change, then two progress frames, then COMPLETED.
        assert events[0] == "job.state_change"  # running
        assert events[1] == "job.progress"
        assert events[2] == "job.progress"
        assert events[-1] == "job.state_change"  # completed
        # All under the same topic.
        assert all(
            c.kwargs["topic"] == TOPIC_SCHEDULED_UPDATES
            for c in mock_bcast.call_args_list
        )

    @patch(BROADCAST_TARGET)
    def test_failed_run_fires_running_then_failed_state_changes(self, mock_bcast):
        @scheduled_job(
            "bcast-fail",
            display_name="bcast fail",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            raise RuntimeError("boom")

        job = ScheduledJob.objects.create(
            key="bcast-fail",
            display_name="bcast fail",
        )
        _execute_job(job, JOB_REGISTRY["bcast-fail"])

        events = [c.kwargs["event"] for c in mock_bcast.call_args_list]
        # RUNNING state change first, then the FAILED alert.raised, then FAILED state change.
        assert events[0] == "job.state_change"
        assert "alert.raised" in events
        assert events[-1] == "job.state_change"

    @patch(BROADCAST_TARGET)
    def test_paused_run_fires_running_then_paused_state_changes(self, mock_bcast):
        @scheduled_job(
            "bcast-pause",
            display_name="bcast pause",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            ScheduledJob.objects.filter(pk=job.pk).update(pause_token=True)
            checkpoint(progress_pct=40.0)

        job = ScheduledJob.objects.create(
            key="bcast-pause",
            display_name="bcast pause",
        )
        _execute_job(job, JOB_REGISTRY["bcast-pause"])

        state_changes = [
            c.kwargs["payload"].get("state")
            for c in mock_bcast.call_args_list
            if c.kwargs["event"] == "job.state_change"
        ]
        # running → paused (no "completed" in between).
        assert state_changes[0] == JOB_STATE_RUNNING
        assert state_changes[-1] == JOB_STATE_PAUSED

    @patch(BROADCAST_TARGET)
    def test_progress_fires_on_every_checkpoint(self, mock_bcast):
        @scheduled_job(
            "bcast-progress",
            display_name="progress frames",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            for pct in (10.0, 25.0, 50.0, 80.0):
                checkpoint(progress_pct=pct)

        job = ScheduledJob.objects.create(
            key="bcast-progress",
            display_name="progress frames",
        )
        _execute_job(job, JOB_REGISTRY["bcast-progress"])

        progress_events = [
            c for c in mock_bcast.call_args_list
            if c.kwargs["event"] == "job.progress"
        ]
        assert len(progress_events) == 4
        pcts = [c.kwargs["payload"]["progress_pct"] for c in progress_events]
        assert pcts == [10.0, 25.0, 50.0, 80.0]


# ─────────────────────────────────────────────────────────────────────
# Alerts integration — verify raise/resolve/ack fire the right events
# ─────────────────────────────────────────────────────────────────────


class AlertsBroadcastWiringTests(TestCase):
    @patch(BROADCAST_TARGET)
    def test_raise_alert_fires_alert_raised(self, mock_bcast):
        raise_alert(
            job_key="feedback_aggregator_ema_refresh",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
            message="window missed",
        )
        events = [c.kwargs["event"] for c in mock_bcast.call_args_list]
        assert "alert.raised" in events

    @patch(BROADCAST_TARGET)
    def test_resolve_sweep_fires_alert_resolved(self, mock_bcast):
        raise_alert(
            job_key="lda_topic_refresh",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
        )
        mock_bcast.reset_mock()

        resolve_open_alerts_for_job("lda_topic_refresh")

        events = [c.kwargs["event"] for c in mock_bcast.call_args_list]
        assert "alert.resolved" in events

    @patch(BROADCAST_TARGET)
    def test_resolve_without_any_open_does_not_broadcast(self, mock_bcast):
        resolve_open_alerts_for_job("nobody-has-alerts-for-this-key")
        # No row touched → no event.
        mock_bcast.assert_not_called()

    @patch(BROADCAST_TARGET)
    def test_acknowledge_fires_alert_acknowledged(self, mock_bcast):
        alert, _ = raise_alert(
            job_key="crawl_freshness_scan",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
        )
        mock_bcast.reset_mock()

        acknowledge(alert.pk)

        events = [c.kwargs["event"] for c in mock_bcast.call_args_list]
        assert "alert.acknowledged" in events

    @patch(BROADCAST_TARGET)
    def test_acknowledge_twice_only_broadcasts_once(self, mock_bcast):
        alert, _ = raise_alert(
            job_key="hits_refresh",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=TODAY,
        )
        mock_bcast.reset_mock()

        acknowledge(alert.pk)
        acknowledge(alert.pk)

        events = [
            c.kwargs["event"] for c in mock_bcast.call_args_list
            if c.kwargs["event"] == "alert.acknowledged"
        ]
        assert len(events) == 1
