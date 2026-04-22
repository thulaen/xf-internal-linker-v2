"""Core middleware — lightweight per-request hooks.

Keep this file intentionally small. Heavy work (imports, DB writes with
joins, external calls) must not run on every request. Only add handlers
that either (a) touch a single indexed row, or (b) are cheap enough to
run unconditionally on authenticated traffic.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class UserActivityMiddleware:
    """Stamps ``UserActivity.last_seen_at`` on every authenticated request.

    Used by the ``/api/auth/active-users/`` endpoint (dashboard
    "whos on shift" widget) to know who has been active in the last
    few minutes. One ``update_or_create`` per request — safe because
    ``user_id`` is indexed and the row is a single unique key.

    Anonymous requests (login page, passkey probe, static assets) are
    a no-op. If the table does not exist yet (first boot before the
    migration applied) we swallow the DoesNotExist/ProgrammingError so
    the request still succeeds — Django startup never blocks on UX
    telemetry.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            self._touch(user, request)
        return response

    @staticmethod
    def _touch(user, request) -> None:
        from django.db import DatabaseError
        from django.utils import timezone

        from .models import UserActivity

        try:
            UserActivity.objects.update_or_create(
                user=user,
                defaults={
                    "last_seen_at": timezone.now(),
                    "last_route": (request.path or "")[:200],
                },
            )
        except DatabaseError:
            # Table missing during pre-migration boot, or transient DB
            # outage. Never let a telemetry write break the request.
            logger.debug("UserActivity touch skipped", exc_info=True)
