"""Postgres slow-query → AutoIssue picker.

Closes a gap that neither GlitchTip (Sentry SDK) nor Pyroscope catches:
queries that get slower over time without crashing. Reads the
`pg_stat_statements` view (extension preloaded via postgres.conf) and
surfaces the top-K queries by total time-per-call when their mean exec
time exceeds a threshold.

Cross-source dedup via `services.dedup.upsert_dedup` — same `queryid`
becomes a stable canonical fingerprint, so a slow query that's ALSO
caught by Sentry as "slow transaction" merges onto one AutoIssue row.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from django.db import connection
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)

# Surface only queries whose MEAN exec time exceeds this threshold.
# Raised from 100 → 250 ms so the postgres-exporter scraping query (a
# genuine slow query that ISN'T an app problem) doesn't dominate the
# AutoIssue list. App queries that genuinely need fixing are far over
# 250 ms; noise from infrastructure scrapers stays below.
_MIN_MEAN_EXEC_MS = 250.0
_MAX_PER_RUN = 10

# SQL fragments whose presence in `query` text means "infrastructure /
# observability tooling" — not an app bug. Filtered out of the slow-
# query picker's input. Add new patterns when a new noise source shows
# up, but keep the list small + targeted; over-filtering hides real bugs.
_NOISE_FRAGMENTS = (
    "pg_stat_",
    "pg_database_size",
    "pg_relation_size",
    "pg_total_relation_size",
    "pg_index",
    "current_database()",
    "pg_indexes_size",
    "pg_namespace",
    "pg_class",
    "pg_constraint",
    "information_schema",
)


@dataclass(frozen=True)
class SlowQuery:
    """One row from pg_stat_statements after thresholding."""

    queryid: int
    query: str
    calls: int
    total_exec_ms: float
    mean_exec_ms: float
    max_exec_ms: float


def _is_app_query(query: str) -> bool:
    """Reject queries whose text contains any infrastructure-tooling fragment."""
    lowered = query.lower()
    return not any(frag in lowered for frag in _NOISE_FRAGMENTS)


def _fetch_slow_queries(min_mean_ms: float, limit: int) -> list[SlowQuery]:
    """SELECT from pg_stat_statements with the slow-only filter.

    Filters out infrastructure/observability scraping queries (postgres-
    exporter, pg_stat_statements introspection, information_schema lookups)
    that are slow by design and would otherwise dominate the picker output.
    """
    sql = """
        SELECT queryid, query, calls,
               total_exec_time AS total_exec_ms,
               mean_exec_time AS mean_exec_ms,
               max_exec_time AS max_exec_ms
        FROM pg_stat_statements
        WHERE mean_exec_time > %s
          AND query NOT ILIKE '%%pg_stat_statements%%'
        ORDER BY total_exec_time DESC
        LIMIT %s
    """
    out: list[SlowQuery] = []
    with connection.cursor() as cur:
        try:
            cur.execute(sql, [min_mean_ms, limit * 5])
        except Exception as exc:
            logger.warning(
                "[slow_query_picker] pg_stat_statements unavailable: %s", exc
            )
            return out
        for row in cur.fetchall():
            query_text = str(row[1] or "")[:512]
            if not _is_app_query(query_text):
                continue
            out.append(
                SlowQuery(
                    queryid=int(row[0] or 0),
                    query=query_text,
                    calls=int(row[2] or 0),
                    total_exec_ms=float(row[3] or 0.0),
                    mean_exec_ms=float(row[4] or 0.0),
                    max_exec_ms=float(row[5] or 0.0),
                )
            )
    return out


def _severity_for(q: SlowQuery) -> str:
    """Map mean exec time onto severity bands."""
    if q.mean_exec_ms >= 5000:
        return AutoIssue.SEVERITY_CRITICAL
    if q.mean_exec_ms >= 1000:
        return AutoIssue.SEVERITY_HIGH
    if q.mean_exec_ms >= 250:
        return AutoIssue.SEVERITY_MEDIUM
    return AutoIssue.SEVERITY_LOW


def _stable_external_id(q: SlowQuery) -> str:
    # SHA1 is non-security here (deduplication fingerprint, not auth/auth)
    raw = f"pg::{q.queryid}".encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


def _format_title(q: SlowQuery) -> str:
    one_line = " ".join(q.query.split())
    return f"Slow query: {one_line[:90]} mean {q.mean_exec_ms:.0f}ms ({q.calls} calls)"


def _upsert_slow_query(q: SlowQuery, priority: float) -> str:
    """Upsert a single slow query through the cross-source dedup helper."""
    title = _format_title(q)
    canonical = canonical_fingerprint(title, "")
    one_line = " ".join(q.query.split())
    description = (
        f"Query (id={q.queryid}): `{one_line[:600]}`\n"
        f"Calls: {q.calls} | total: {q.total_exec_ms:.0f} ms | "
        f"mean: {q.mean_exec_ms:.1f} ms | max: {q.max_exec_ms:.0f} ms.\n"
        f"Surfaced from pg_stat_statements (extension preloaded via "
        f"postgres.conf). To see the full query: "
        f"`SELECT query FROM pg_stat_statements WHERE queryid = {q.queryid};`."
    )
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_AGENT,  # closest fit — it's a backend find
        external_id=_stable_external_id(q),
        fingerprint=_stable_external_id(q),
        title=title,
        description=description,
        affected_files=[],  # query plan is in the DB, not a file
        severity=_severity_for(q),
        priority_score=priority,
        occurrence_count=q.calls,
    )
    return outcome


def _priority_score(q: SlowQuery, max_total: float) -> float:
    """Normalise total_exec_ms to [0, 1] so the picker ranks by aggregate cost."""
    if max_total <= 0:
        return 0.0
    return min(1.0, q.total_exec_ms / max_total)


def pick_slow_queries(*, limit: int = _MAX_PER_RUN) -> dict:
    """Top-K slow queries → AutoIssue (with cross-source dedup)."""
    queries = _fetch_slow_queries(_MIN_MEAN_EXEC_MS, limit)
    if not queries:
        return {
            "status": "ok",
            "fetched": 0,
            "promoted": 0,
            "created": 0,
            "merged": 0,
            "updated": 0,
        }

    max_total = max(q.total_exec_ms for q in queries)
    counts = {"created": 0, "merged": 0, "updated": 0}
    for q in queries[:limit]:
        outcome = _upsert_slow_query(q, _priority_score(q, max_total))
        counts[outcome] = counts.get(outcome, 0) + 1

    logger.info(
        "[auto_issues.slow_query_picker] fetched=%d created=%d merged=%d updated=%d",
        len(queries), counts["created"], counts["merged"], counts["updated"],
    )
    return {
        "status": "ok",
        "fetched": len(queries),
        "promoted": sum(counts.values()),
        **counts,
    }
