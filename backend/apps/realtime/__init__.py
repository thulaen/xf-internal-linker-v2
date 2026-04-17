"""
Realtime app — generic topic-based WebSocket push.

Phase R0 of the approved plan at C:\\Users\\goldm\\.claude\\plans\\robust-floating-cerf.md.

Public API:
    from apps.realtime.services import broadcast

    broadcast("diagnostics", "service.status.changed", {"service": "redis", "state": "healthy"})

Topics are strings using letters, digits, underscores, periods, or hyphens.
Frontend clients connect once to /ws/realtime/ and subscribe/unsubscribe to
topics dynamically. See docs/REALTIME.md for the add-a-new-area recipe.
"""

default_app_config = "apps.realtime.apps.RealtimeConfig"
