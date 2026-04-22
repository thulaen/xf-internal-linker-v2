"""REST API for the Scheduled Updates orchestrator (PR-B.5).

Four job actions and one alert action — all state mutation happens
through these endpoints, never a generic PATCH:

- GET  /api/scheduled-updates/jobs/                list all jobs
- GET  /api/scheduled-updates/jobs/<id>/           detail
- POST /api/scheduled-updates/jobs/<id>/pause      set pause_token=True
- POST /api/scheduled-updates/jobs/<id>/resume     clear pause_token, state→pending
- POST /api/scheduled-updates/jobs/<id>/cancel     force state→failed
- POST /api/scheduled-updates/jobs/<id>/run-now    set scheduled_for=now (window-respecting)

- GET  /api/scheduled-updates/alerts/              list alerts (active by default)
- POST /api/scheduled-updates/alerts/<id>/acknowledge

Every action returns the fresh model row so the caller can update
its cache without a second round-trip. All mutations also emit a
WebSocket broadcast via apps.realtime so other clients see the change
immediately.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, views
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .alerts import acknowledge, active_alerts_qs
from .broadcasts import broadcast_state_change
from .models import (
    JOB_STATE_FAILED,
    JOB_STATE_PAUSED,
    JOB_STATE_PENDING,
    JOB_STATE_RUNNING,
    JobAlert,
    ScheduledJob,
)
from .serializers import JobAlertSerializer, ScheduledJobSerializer
from .window import (
    is_within_window,
    seconds_remaining_in_window,
    time_until_window_opens,
    would_overflow,
)


# ─────────────────────────────────────────────────────────────────────
# Jobs — list + detail + four actions
# ─────────────────────────────────────────────────────────────────────


class ScheduledJobListView(ListAPIView):
    """GET /api/scheduled-updates/jobs/"""

    permission_classes = [IsAuthenticated]
    serializer_class = ScheduledJobSerializer
    queryset = ScheduledJob.objects.all().order_by("priority", "key")


class ScheduledJobDetailView(RetrieveAPIView):
    """GET /api/scheduled-updates/jobs/<id>/"""

    permission_classes = [IsAuthenticated]
    serializer_class = ScheduledJobSerializer
    queryset = ScheduledJob.objects.all()


def _respond_job(job: ScheduledJob) -> Response:
    """Shared response shape for the four action endpoints."""
    return Response(ScheduledJobSerializer(job).data)


class ScheduledJobPauseView(views.APIView):
    """POST /api/scheduled-updates/jobs/<id>/pause"""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        job = get_object_or_404(ScheduledJob, pk=pk)
        if job.pause_token:
            return _respond_job(job)  # idempotent no-op
        job.pause_token = True
        job.save(update_fields=["pause_token", "updated_at"])
        # Note: no state flip here — the actual RUNNING → PAUSED
        # transition happens inside runner._execute_job the next time
        # the job hits a checkpoint. The UI shows "Pausing…" until
        # the state_change broadcast lands.
        return _respond_job(job)


class ScheduledJobResumeView(views.APIView):
    """POST /api/scheduled-updates/jobs/<id>/resume"""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        job = get_object_or_404(ScheduledJob, pk=pk)
        if job.state != JOB_STATE_PAUSED:
            return Response(
                {
                    "detail": (
                        f"Cannot resume: job is in state '{job.state}'. "
                        f"Resume is only valid from 'paused'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        job.pause_token = False
        job.state = JOB_STATE_PENDING
        job.progress_pct = 0.0
        job.current_message = "Pending resume…"
        job.save(
            update_fields=[
                "pause_token",
                "state",
                "progress_pct",
                "current_message",
                "updated_at",
            ]
        )
        broadcast_state_change(job)
        return _respond_job(job)


class ScheduledJobCancelView(views.APIView):
    """POST /api/scheduled-updates/jobs/<id>/cancel

    Force-transitions a job to FAILED. Safe from any state; the runner
    picks up the change at its next checkpoint (via pause_token) or
    ignores the row (if not currently running).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        job = get_object_or_404(ScheduledJob, pk=pk)
        if job.state == JOB_STATE_RUNNING:
            # Set the pause_token so the checkpoint raises PauseRequested,
            # and tag a cancellation message. The runner's PAUSED branch
            # will pick it up; a follow-up acknowledge can upgrade it to
            # FAILED if desired.
            job.pause_token = True
            job.current_message = "Cancellation requested by operator."
            job.save(update_fields=["pause_token", "current_message", "updated_at"])
            return _respond_job(job)
        # Not running — flip directly to FAILED.
        job.state = JOB_STATE_FAILED
        job.finished_at = timezone.now()
        job.current_message = "Cancelled by operator."
        job.pause_token = False
        job.save(
            update_fields=[
                "state",
                "finished_at",
                "current_message",
                "pause_token",
                "updated_at",
            ]
        )
        broadcast_state_change(job)
        return _respond_job(job)


class ScheduledJobRunNowView(views.APIView):
    """POST /api/scheduled-updates/jobs/<id>/run-now

    Nudges a job to be picked by the runner at its next tick.
    Respects the window guard: if we're outside 13:00-23:00 or the
    job's duration_estimate would overflow 23:00, returns 409 with
    a helpful time-until-open hint.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        job = get_object_or_404(ScheduledJob, pk=pk)
        if not is_within_window():
            delta = time_until_window_opens()
            return Response(
                {
                    "detail": (
                        "Outside the 13:00-23:00 window. "
                        f"Opens in {int(delta.total_seconds() // 60)} minute(s)."
                    ),
                    "seconds_until_window_opens": int(delta.total_seconds()),
                },
                status=status.HTTP_409_CONFLICT,
            )
        if would_overflow(job.duration_estimate_sec):
            return Response(
                {
                    "detail": (
                        f"Job would not finish before 23:00 "
                        f"(duration estimate {job.duration_estimate_sec}s, "
                        f"window closes in {seconds_remaining_in_window()}s)."
                    ),
                    "seconds_remaining_in_window": seconds_remaining_in_window(),
                },
                status=status.HTTP_409_CONFLICT,
            )
        job.state = JOB_STATE_PENDING
        job.scheduled_for = timezone.now()
        job.save(update_fields=["state", "scheduled_for", "updated_at"])
        broadcast_state_change(job)
        return _respond_job(job)


# ─────────────────────────────────────────────────────────────────────
# Alerts — list + acknowledge
# ─────────────────────────────────────────────────────────────────────


class AlertListView(ListAPIView):
    """GET /api/scheduled-updates/alerts/

    Default: active only (not acknowledged, not resolved). Pass
    ``?include=all`` for the full history, or ``?include=resolved``
    for the resolved-and-dropped-off-the-badge rows.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = JobAlertSerializer

    def get_queryset(self):
        mode = self.request.query_params.get("include", "active")
        if mode == "all":
            return JobAlert.objects.all().order_by("-first_raised_at")
        if mode == "resolved":
            return JobAlert.objects.filter(
                resolved_at__isnull=False,
            ).order_by("-resolved_at")
        return active_alerts_qs().order_by("-first_raised_at")


class AlertAcknowledgeView(views.APIView):
    """POST /api/scheduled-updates/alerts/<id>/acknowledge"""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        alert = acknowledge(pk)
        if alert is None:
            return Response(
                {"detail": f"Alert {pk} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(JobAlertSerializer(alert).data)


# ─────────────────────────────────────────────────────────────────────
# Window status — small helper the dashboard calls on load
# ─────────────────────────────────────────────────────────────────────


class WindowStatusView(views.APIView):
    """GET /api/scheduled-updates/window/

    Returns whether the orchestrator can currently start new jobs,
    plus how long until the next transition. Drives the "next window
    opens in HH:MM" label on the Scheduled Updates tab.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "is_within_window": is_within_window(),
                "seconds_remaining_in_window": seconds_remaining_in_window(),
                "seconds_until_window_opens": int(
                    time_until_window_opens().total_seconds()
                ),
            }
        )
