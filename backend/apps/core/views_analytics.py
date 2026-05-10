"""
Authenticated user activity analytics view extracted from ``views_capacity.py``.
Part of the domain-driven decomposition to stay under the 1500-line cap.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class ActiveUsersView(APIView):
    """GET /api/auth/active-users/ — who has made an authenticated request recently."""

    permission_classes = [IsAuthenticated]
    ACTIVE_WINDOW_MIN = 5

    def get(self, request):
        from .models import UserActivity

        cutoff = timezone.now() - timedelta(minutes=self.ACTIVE_WINDOW_MIN)
        rows = (
            UserActivity.objects.filter(last_seen_at__gte=cutoff)
            .select_related("user")
            .order_by("-last_seen_at")
        )
        payload = [
            {
                "username": r.user.username,
                "last_seen": r.last_seen_at.isoformat(),
                "route": r.last_route,
            }
            for r in rows
        ]
        return Response(payload)
