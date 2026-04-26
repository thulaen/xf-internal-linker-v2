"""Tests for the Scheduled Updates REST API (PR-B.5)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    ALERT_TYPE_MISSED,
    JOB_PRIORITY_HIGH,
    JOB_STATE_COMPLETED,
    JOB_STATE_FAILED,
    JOB_STATE_PAUSED,
    JOB_STATE_PENDING,
    JOB_STATE_RUNNING,
    JobAlert,
    ScheduledJob,
)


User = get_user_model()


class _AuthedTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="operator",
            password="pw",
        )
        self.client.force_authenticate(user=self.user)


# ─────────────────────────────────────────────────────────────────────
# /jobs/ list + detail
# ─────────────────────────────────────────────────────────────────────


class JobListDetailTests(_AuthedTestCase):
    def test_list_requires_auth(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get("/api/scheduled-updates/jobs/")
        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_list_returns_all_jobs(self) -> None:
        ScheduledJob.objects.create(key="a", display_name="A")
        ScheduledJob.objects.create(key="b", display_name="B")

        resp = self.client.get("/api/scheduled-updates/jobs/")
        assert resp.status_code == status.HTTP_200_OK

        keys = {row["key"] for row in resp.data["results"]} if "results" in resp.data else {
            row["key"] for row in resp.data
        }
        assert keys == {"a", "b"}

    def test_detail_returns_single_job(self) -> None:
        job = ScheduledJob.objects.create(
            key="detail-check",
            display_name="Detail check",
            priority=JOB_PRIORITY_HIGH,
        )
        resp = self.client.get(f"/api/scheduled-updates/jobs/{job.pk}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["key"] == "detail-check"
        assert resp.data["priority"] == JOB_PRIORITY_HIGH


# ─────────────────────────────────────────────────────────────────────
# /pause + /resume
# ─────────────────────────────────────────────────────────────────────


class PauseResumeTests(_AuthedTestCase):
    def test_pause_sets_pause_token_without_state_flip(self) -> None:
        job = ScheduledJob.objects.create(
            key="pause-me",
            display_name="Pause me",
            state=JOB_STATE_RUNNING,
        )
        resp = self.client.post(f"/api/scheduled-updates/jobs/{job.pk}/pause/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["pause_token"] is True
        # State does NOT flip here; runner handles the transition.
        assert resp.data["state"] == JOB_STATE_RUNNING

    def test_pause_is_idempotent(self) -> None:
        job = ScheduledJob.objects.create(
            key="pause-idem",
            display_name="Pause idem",
            pause_token=True,
        )
        resp = self.client.post(f"/api/scheduled-updates/jobs/{job.pk}/pause/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["pause_token"] is True

    def test_resume_from_paused_goes_to_pending(self) -> None:
        job = ScheduledJob.objects.create(
            key="resume-me",
            display_name="Resume me",
            state=JOB_STATE_PAUSED,
            pause_token=True,
            progress_pct=60.0,
        )
        resp = self.client.post(f"/api/scheduled-updates/jobs/{job.pk}/resume/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["state"] == JOB_STATE_PENDING
        assert resp.data["pause_token"] is False
        assert resp.data["progress_pct"] == 0.0

    def test_resume_rejects_non_paused_job(self) -> None:
        job = ScheduledJob.objects.create(
            key="resume-invalid",
            display_name="Resume invalid",
            state=JOB_STATE_COMPLETED,
        )
        resp = self.client.post(f"/api/scheduled-updates/jobs/{job.pk}/resume/")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ─────────────────────────────────────────────────────────────────────
# /cancel
# ─────────────────────────────────────────────────────────────────────


class CancelTests(_AuthedTestCase):
    def test_cancel_running_sets_pause_token(self) -> None:
        job = ScheduledJob.objects.create(
            key="cancel-running",
            display_name="Cancel running",
            state=JOB_STATE_RUNNING,
        )
        resp = self.client.post(f"/api/scheduled-updates/jobs/{job.pk}/cancel/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["pause_token"] is True
        # State stays RUNNING until the runner's next checkpoint.
        assert resp.data["state"] == JOB_STATE_RUNNING

    def test_cancel_non_running_flips_to_failed(self) -> None:
        job = ScheduledJob.objects.create(
            key="cancel-pending",
            display_name="Cancel pending",
            state=JOB_STATE_PENDING,
        )
        resp = self.client.post(f"/api/scheduled-updates/jobs/{job.pk}/cancel/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["state"] == JOB_STATE_FAILED
        assert resp.data["finished_at"] is not None


# ─────────────────────────────────────────────────────────────────────
# /run-now
# ─────────────────────────────────────────────────────────────────────


class RunNowTests(_AuthedTestCase):
    @patch("apps.scheduled_updates.views.is_within_window", return_value=True)
    @patch("apps.scheduled_updates.views.would_overflow", return_value=False)
    def test_run_now_within_window_sets_scheduled_for(self, *_):
        job = ScheduledJob.objects.create(
            key="run-now",
            display_name="Run now",
            state=JOB_STATE_COMPLETED,
        )
        resp = self.client.post(f"/api/scheduled-updates/jobs/{job.pk}/run-now/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["state"] == JOB_STATE_PENDING
        assert resp.data["scheduled_for"] is not None

    @patch("apps.scheduled_updates.views.is_within_window", return_value=False)
    @patch(
        "apps.scheduled_updates.views.time_until_window_opens",
        return_value=dt.timedelta(hours=3),
    )
    def test_run_now_outside_window_returns_409(self, *_):
        job = ScheduledJob.objects.create(
            key="outside-window",
            display_name="Outside window",
        )
        resp = self.client.post(f"/api/scheduled-updates/jobs/{job.pk}/run-now/")
        assert resp.status_code == status.HTTP_409_CONFLICT
        assert "seconds_until_window_opens" in resp.data

    @patch("apps.scheduled_updates.views.is_within_window", return_value=True)
    @patch("apps.scheduled_updates.views.would_overflow", return_value=True)
    @patch(
        "apps.scheduled_updates.views.seconds_remaining_in_window",
        return_value=120,
    )
    def test_run_now_when_overflow_returns_409(self, *_):
        job = ScheduledJob.objects.create(
            key="would-overflow",
            display_name="Would overflow",
            duration_estimate_sec=600,
        )
        resp = self.client.post(f"/api/scheduled-updates/jobs/{job.pk}/run-now/")
        assert resp.status_code == status.HTTP_409_CONFLICT
        assert "seconds_remaining_in_window" in resp.data


# ─────────────────────────────────────────────────────────────────────
# /alerts/
# ─────────────────────────────────────────────────────────────────────


class AlertApiTests(_AuthedTestCase):
    def test_default_list_shows_only_active(self) -> None:
        active = JobAlert.objects.create(
            job_key="a-active",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=dt.date(2026, 4, 22),
        )
        JobAlert.objects.create(
            job_key="a-resolved",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=dt.date(2026, 4, 22),
            resolved_at="2026-04-22T15:00:00+00:00",
        )

        resp = self.client.get("/api/scheduled-updates/alerts/")
        assert resp.status_code == status.HTTP_200_OK
        rows = resp.data["results"] if "results" in resp.data else resp.data
        ids = {row["id"] for row in rows}
        assert ids == {active.pk}

    def test_include_all_shows_everything(self) -> None:
        JobAlert.objects.create(
            job_key="b-active",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=dt.date(2026, 4, 22),
        )
        JobAlert.objects.create(
            job_key="b-resolved",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=dt.date(2026, 4, 22),
            resolved_at="2026-04-22T15:00:00+00:00",
        )
        resp = self.client.get("/api/scheduled-updates/alerts/?include=all")
        rows = resp.data["results"] if "results" in resp.data else resp.data
        assert len(rows) == 2

    def test_acknowledge_ok(self) -> None:
        alert = JobAlert.objects.create(
            job_key="ack-me",
            alert_type=ALERT_TYPE_MISSED,
            calendar_date=dt.date(2026, 4, 22),
        )
        resp = self.client.post(
            f"/api/scheduled-updates/alerts/{alert.pk}/acknowledge/"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["acknowledged_at"] is not None

    def test_acknowledge_unknown_returns_404(self) -> None:
        resp = self.client.post("/api/scheduled-updates/alerts/999999/acknowledge/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ─────────────────────────────────────────────────────────────────────
# /window/
# ─────────────────────────────────────────────────────────────────────


class WindowStatusTests(_AuthedTestCase):
    def test_returns_all_three_fields(self) -> None:
        resp = self.client.get("/api/scheduled-updates/window/")
        assert resp.status_code == status.HTTP_200_OK
        assert set(resp.data.keys()) == {
            "is_within_window",
            "seconds_remaining_in_window",
            "seconds_until_window_opens",
        }
        assert isinstance(resp.data["is_within_window"], bool)
