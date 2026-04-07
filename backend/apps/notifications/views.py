"""
Notification REST API views.

GET  /api/notifications/alerts/                 — list alerts (filterable)
GET  /api/notifications/alerts/summary/         — unread counts by severity
POST /api/notifications/alerts/<uuid>/read/     — mark one alert read
POST /api/notifications/alerts/<uuid>/acknowledge/  — acknowledge one alert
POST /api/notifications/alerts/<uuid>/resolve/  — resolve one alert
POST /api/notifications/alerts/acknowledge-all/ — acknowledge all unread/read
GET  /api/settings/notifications/               — get notification preferences
PUT  /api/settings/notifications/               — update notification preferences
POST /api/notifications/test/                   — fire a synthetic test alert
"""

import json
import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AppSetting

from .models import OperatorAlert
from .serializers import OperatorAlertSerializer
from .services import emit_operator_alert, get_unread_summary

logger = logging.getLogger(__name__)

_PREFS_KEY = "notifications.settings"
_PREFS_DEFAULT = {
    "desktop_enabled": True,
    "sound_enabled": True,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "min_desktop_severity": "warning",
    "min_sound_severity": "error",
    "enable_job_completed": True,
    "enable_job_failed": True,
    "enable_job_stalled": True,
    "enable_model_status": True,
    "enable_gsc_spikes": True,
    "toast_enabled": True,
    "toast_min_severity": "warning",
    "duplicate_cooldown_seconds": 900,
    "job_stalled_default_minutes": 15,
    "gsc_spike_min_impressions_delta": 50,
    "gsc_spike_min_clicks_delta": 5,
    "gsc_spike_min_relative_lift": 0.5,
}


def _load_prefs() -> dict:
    try:
        setting = AppSetting.objects.get(key=_PREFS_KEY)
        return json.loads(setting.value)
    except AppSetting.DoesNotExist:
        return dict(_PREFS_DEFAULT)
    except Exception:
        return dict(_PREFS_DEFAULT)


def _save_prefs(data: dict) -> dict:
    merged = {**_PREFS_DEFAULT, **data}
    AppSetting.objects.update_or_create(
        key=_PREFS_KEY,
        defaults={
            "value": json.dumps(merged),
            "value_type": "json",
            "category": "general",
            "description": "Operator notification delivery preferences.",
        },
    )
    return merged


class AlertListView(APIView):
    """List operator alerts with optional filters."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = OperatorAlert.objects.all()

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        severity_filter = request.query_params.get("severity")
        if severity_filter:
            qs = qs.filter(severity=severity_filter)

        event_type_filter = request.query_params.get("event_type")
        if event_type_filter:
            qs = qs.filter(event_type=event_type_filter)

        source_area_filter = request.query_params.get("source_area")
        if source_area_filter:
            qs = qs.filter(source_area=source_area_filter)

        qs = qs.select_related("error_log").prefetch_related("delivery_attempts")
        serializer = OperatorAlertSerializer(qs[:200], many=True)
        return Response(serializer.data)


class AlertSummaryView(APIView):
    """Return unread counts by severity plus the latest alert timestamp."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_unread_summary())


class AlertReadView(APIView):
    """Mark a single alert as read."""

    permission_classes = [IsAuthenticated]

    def post(self, request, alert_id):
        try:
            alert = OperatorAlert.objects.get(alert_id=alert_id)
        except OperatorAlert.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if alert.status == OperatorAlert.STATUS_UNREAD:
            alert.status = OperatorAlert.STATUS_READ
            alert.read_at = timezone.now()
            alert.save(update_fields=["status", "read_at"])
        return Response(OperatorAlertSerializer(alert).data)


class AlertAcknowledgeView(APIView):
    """Acknowledge (dismiss) a single alert."""

    permission_classes = [IsAuthenticated]

    def post(self, request, alert_id):
        try:
            alert = OperatorAlert.objects.get(alert_id=alert_id)
        except OperatorAlert.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if alert.status != OperatorAlert.STATUS_ACKNOWLEDGED:
            alert.status = OperatorAlert.STATUS_ACKNOWLEDGED
            alert.acknowledged_at = timezone.now()
            alert.save(update_fields=["status", "acknowledged_at"])
        return Response(OperatorAlertSerializer(alert).data)


class AlertResolveView(APIView):
    """Mark a single alert as resolved (condition cleared)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, alert_id):
        try:
            alert = OperatorAlert.objects.get(alert_id=alert_id)
        except OperatorAlert.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if alert.status != OperatorAlert.STATUS_RESOLVED:
            alert.status = OperatorAlert.STATUS_RESOLVED
            alert.resolved_at = timezone.now()
            alert.save(update_fields=["status", "resolved_at"])
        return Response(OperatorAlertSerializer(alert).data)


class AlertAcknowledgeAllView(APIView):
    """Acknowledge all unread and read alerts at once."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        now = timezone.now()
        updated = OperatorAlert.objects.filter(
            status__in=[OperatorAlert.STATUS_UNREAD, OperatorAlert.STATUS_READ]
        ).update(status=OperatorAlert.STATUS_ACKNOWLEDGED, acknowledged_at=now)
        return Response({"acknowledged": updated})


class NotificationPreferencesView(APIView):
    """Read and update notification delivery preferences."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_load_prefs())

    def put(self, request):
        saved = _save_prefs(request.data)
        return Response(saved)


class TestNotificationView(APIView):
    """Fire a synthetic alert so the operator can test bell, toast, and sound."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        severity = request.data.get("severity", OperatorAlert.SEVERITY_WARNING)
        if severity not in dict(OperatorAlert.SEVERITY_CHOICES):
            severity = OperatorAlert.SEVERITY_WARNING

        alert = emit_operator_alert(
            event_type="system.test",
            severity=severity,
            title="Test notification",
            message="This is a test alert fired from the notification settings.",
            source_area=OperatorAlert.AREA_SYSTEM,
            dedupe_key=f"system.test:{timezone.now().strftime('%Y%m%d%H%M')}",
            related_route="/settings",
        )
        return Response(OperatorAlertSerializer(alert).data, status=status.HTTP_201_CREATED)
