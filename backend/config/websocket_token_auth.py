"""Token-aware WebSocket auth middleware.

Adds DRF token auth support for browser WebSocket handshakes by reading
`?token=<key>` from the connection URL. Session/cookie auth still runs via
AuthMiddlewareStack; this middleware only fills in the user when the scope
is still anonymous.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from rest_framework.authtoken.models import Token


@database_sync_to_async
def _get_user_for_token(token_key: str):
    try:
        return Token.objects.select_related("user").get(key=token_key).user
    except Token.DoesNotExist:
        return AnonymousUser()


class QueryStringTokenAuthMiddleware:
    """Populate ``scope['user']`` from a ``?token=`` query parameter."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        user = scope.get("user")
        if user is None or not getattr(user, "is_authenticated", False):
            query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
            token_key = query.get("token", [None])[0]
            if token_key:
                scope = {**scope, "user": await _get_user_for_token(token_key)}
        return await self.inner(scope, receive, send)
