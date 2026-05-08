"""Phase 2.18 — fast read of pre-aggregated dashboard counts.

Returns the suggestion-status histogram from the
``dashboard_suggestion_counts_mv`` materialised view (refreshed every 5 min by
``apps.core.tasks_dashboard.refresh_dashboard_matviews``). When the matview
hasn't been created yet (fresh install pre-migration) or the SQL fails for
any reason, falls back to the live aggregate so the dashboard never breaks.

Citation: PostgreSQL docs §38.3.

Plain-English: instead of running a SUM/GROUP BY against the full
``suggestions_suggestion`` table on every dashboard refresh, we keep a tiny
pre-computed table with one row per status. The dashboard reads from there
in microseconds. The pre-computed table refreshes on a background timer so
it stays fresh enough for operator decisions without paying the per-refresh
query cost.
"""

from __future__ import annotations

import logging

from django.db import DatabaseError, connection

from apps.core.services.cache_policy import record_event

logger = logging.getLogger(__name__)


# Approximate payload size for one suggestion-status histogram (~6 statuses
# × 24 bytes per ``{"status": int}`` row when JSON-encoded). Used for the
# cache-policy size estimate; exact byte count would require serialising
# the dict on every call which defeats the purpose of the matview.
_DASHBOARD_PAYLOAD_BYTES = 256


def _emit_cache_event(event: str) -> None:
    """Tiny wrapper so callers don't repeat the kwarg list."""
    record_event(
        "dashboard",
        event,
        key="suggestion_status_counts",
        bytes_size=_DASHBOARD_PAYLOAD_BYTES,
    )


def _read_status_counts_matview() -> dict[str, int] | None:
    """Read the pre-aggregated histogram. Returns ``None`` on any failure.

    A ``None`` return means the caller must fall back to the live ORM
    aggregate. The cache-policy event is also emitted so the operator
    sees both the fast and the slow paths on ``/diagnostics``.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status, count FROM dashboard_suggestion_counts_mv")
            rows = cursor.fetchall()
        _emit_cache_event("hit")
        return {status: int(count) for status, count in rows}
    except DatabaseError:
        logger.debug(
            "dashboard_suggestion_counts_mv unavailable; falling back to live aggregate",
            exc_info=True,
        )
        _emit_cache_event("miss")
        return None
    except Exception:  # noqa: BLE001 — fallback path is the visible signal; the warn-log surfaces unexpected errors.
        logger.warning(
            "dashboard_suggestion_counts_mv read failed; falling back to live aggregate",
            exc_info=True,
        )
        _emit_cache_event("miss")
        return None


def _read_status_counts_live() -> dict[str, int]:
    """Live ORM aggregate fallback. Returns empty dict on total failure."""
    try:
        from django.db.models import Count

        from apps.suggestions.models import Suggestion

        rows = Suggestion.objects.values("status").annotate(count=Count("pk"))
        return {row["status"]: int(row["count"]) for row in rows}
    except Exception:  # noqa: BLE001 — empty dict is the contract on total failure; callers treat no-data identically to no-suggestions.
        logger.warning(
            "Live suggestion-status aggregate also failed; returning empty dict",
            exc_info=True,
        )
        return {}


def get_suggestion_status_counts() -> dict[str, int]:
    """Return ``{status: count}`` for every suggestion status.

    Reads from ``dashboard_suggestion_counts_mv`` first; falls back to the
    live ``Suggestion.objects.values("status").annotate(count=Count(...))``
    aggregate if the matview is unavailable. Empty dict on total failure
    so callers can treat "no data" identically to "no suggestions".

    Plain-English: every read here also pings the cache-policy meter so
    operators can see the matview's hit ratio on ``/diagnostics`` (Phase
    4.13). A "hit" is the fast matview path; a "miss" means the matview
    was unavailable and we paid for a live aggregate.
    """
    cached = _read_status_counts_matview()
    if cached is not None:
        return cached
    return _read_status_counts_live()


def refresh_suggestion_counts_matview(*, concurrently: bool = True) -> bool:
    """Refresh the dashboard matview. Returns True on success, False on failure.

    ``concurrently=True`` uses ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` so
    readers are not blocked. Concurrent refresh requires a unique index
    (created by migration ``core/0018``); falls back to a non-concurrent
    refresh if the index is missing.
    """
    sql_concurrent = (
        "REFRESH MATERIALIZED VIEW CONCURRENTLY dashboard_suggestion_counts_mv"
    )
    sql_blocking = "REFRESH MATERIALIZED VIEW dashboard_suggestion_counts_mv"

    statement = sql_concurrent if concurrently else sql_blocking
    try:
        with connection.cursor() as cursor:
            cursor.execute(statement)
        return True
    except DatabaseError:
        if concurrently:
            # Concurrent refresh failed (no unique index, lock contention,
            # whatever). Try blocking refresh as a fallback.
            return refresh_suggestion_counts_matview(concurrently=False)
        logger.warning(
            "REFRESH MATERIALIZED VIEW dashboard_suggestion_counts_mv failed",
            exc_info=True,
        )
        return False
    except Exception:
        logger.warning(
            "Unexpected error refreshing dashboard_suggestion_counts_mv",
            exc_info=True,
        )
        return False
