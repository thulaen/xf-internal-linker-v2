from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import ErrorLog

from .models import ServiceStatusSnapshot, SystemConflict


class ServiceStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceStatusSnapshot
        fields = "__all__"


class SystemConflictSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemConflict
        fields = "__all__"


class ErrorLogSerializer(serializers.ModelSerializer):
    """
    Phase GT Step 6. Adds two derived fields to every ErrorLog row:

    - `error_trend` — 7-day bucket counts per fingerprint so the UI can
      render a sparkline showing whether this error is trending up or dying.
    - `related_error_ids` — up to 10 ids of other errors that fired within
      ±5 minutes so the operator doesn't waste time fixing 10 symptoms
      of one root cause.

    The derived fields are computed per row, so keep them cheap: indexed
    lookups only, no `.all()` scans.
    """

    error_trend = serializers.SerializerMethodField()
    related_error_ids = serializers.SerializerMethodField()

    class Meta:
        model = ErrorLog
        fields = "__all__"

    def get_error_trend(self, obj: ErrorLog) -> list[dict]:
        if not obj.fingerprint:
            return []
        start = timezone.now().date() - timedelta(days=6)
        qs = (
            ErrorLog.objects.filter(
                fingerprint=obj.fingerprint, created_at__date__gte=start
            )
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        by_day = {row["day"]: row["count"] for row in qs}
        return [
            {
                "date": str(start + timedelta(days=i)),
                "count": by_day.get(start + timedelta(days=i), 0),
            }
            for i in range(7)
        ]

    def get_related_error_ids(self, obj: ErrorLog) -> list[int]:
        window = timedelta(minutes=5)
        return list(
            ErrorLog.objects.filter(
                created_at__gte=obj.created_at - window,
                created_at__lte=obj.created_at + window,
            )
            .exclude(id=obj.id)
            .values_list("id", flat=True)[:10]
        )
