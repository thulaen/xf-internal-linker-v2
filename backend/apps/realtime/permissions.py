"""
Realtime topic permissions.

Every topic the frontend tries to subscribe to is checked here before the
consumer joins the corresponding Channels group. Keeps authorisation in one
place instead of scattered across every producer.

Default rule: any authenticated user may subscribe. Override here for topics
that leak staff-only or sensitive information.
"""

from __future__ import annotations

from typing import Callable

# Type alias for a permission check. Takes the request user and the requested
# topic name, returns True if the subscription should be allowed.
PermissionCheck = Callable[[object, str], bool]


def _is_staff(user: object, _topic: str) -> bool:
    """Staff-only topics (admin pauses, runtime toggles, etc.)."""
    return bool(getattr(user, "is_staff", False))


def _is_authenticated(user: object, _topic: str) -> bool:
    """Default: anyone logged in."""
    return bool(getattr(user, "is_authenticated", False))


# Exact-match overrides. Prefix-match overrides live in _PREFIX_RULES below.
_EXACT_RULES: dict[str, PermissionCheck] = {
    "settings.runtime": _is_staff,
}

# Longest-prefix wins. Leave empty by default; add entries as new topics land.
_PREFIX_RULES: list[tuple[str, PermissionCheck]] = [
    # ("admin.", _is_staff),  # example — anything under admin.* requires staff
]


def can_subscribe(user: object, topic: str) -> bool:
    """
    Decide whether `user` may subscribe to `topic`.

    Returns True if allowed, False otherwise. Unknown topics default to
    "authenticated user may subscribe" so adding a new topic does not require
    touching this file unless the topic is sensitive.
    """
    if topic in _EXACT_RULES:
        return _EXACT_RULES[topic](user, topic)

    # Longest-prefix match.
    for prefix, check in sorted(_PREFIX_RULES, key=lambda kv: len(kv[0]), reverse=True):
        if topic.startswith(prefix):
            return check(user, topic)

    return _is_authenticated(user, topic)


# Phase RC / Gaps 139-142 — client-side publish authorisation.
# Only collaboration topics (presence / cursor / lock / typing) accept
# direct client publishes. Backend-driven topics like `diagnostics`
# stay producer-restricted so a malicious client can't fake events.
_PUBLISH_PREFIXES: tuple[str, ...] = (
    "presence.",
    "cursor.",
    "lock.",
    "typing.",
)


def can_publish(user: object, topic: str) -> bool:
    """Phase RC / Gaps 139-142 — may this user publish to this topic?

    Authentication required. Topic must be one of the collaboration
    namespaces; everything else is server-emitted only.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    return any(topic.startswith(prefix) for prefix in _PUBLISH_PREFIXES)


__all__ = ["can_subscribe", "can_publish"]
