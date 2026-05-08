"""XF Internal Linker — MCP server.

Exposes a small set of read-only tools to AI agents (Claude Code, Codex,
Antigravity once it ships MCP). Runs inside the existing backend container
so it has the same Django settings + database access as the rest of the app.

Transport: stdio (the most stable transport in the MCP SDK). Claude Code
launches the server via the project-scope `.mcp.json` at the repo root,
which spawns this process with `docker compose exec -T backend python
/app/backend/mcp_server.py` whenever a session opens in this folder.

KISS v1 ships three tools. Adding a tool is a one-function change at the
bottom of this file:

    @mcp.tool()
    def my_new_tool(arg: str) -> dict:
        '''One-line plain-English description.'''
        return {"hello": arg}

The full list of planned tools (per docs/MCP-SETUP.md) lands incrementally —
keep tools small, single-purpose, and read-only by default. Write tools need
explicit operator-token auth and don't ship in v1.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _bootstrap_django() -> None:
    """Wire up Django so we can call the ORM from inside the MCP process."""
    # The container's PYTHONPATH includes /app/backend already, but be defensive
    # in case this file is invoked from somewhere else during local debugging.
    backend_root = os.path.dirname(os.path.abspath(__file__))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
    import django  # noqa: PLC0415

    django.setup()


# Bootstrap before importing anything that touches Django models.
_bootstrap_django()


try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.stderr.write(
        "mcp_server: the 'mcp' Python package is not installed.\n"
        "Install it via: pip install mcp\n"
        "(it's pinned in backend/requirements.txt and the docker image rebuilds with it.)\n"
    )
    sys.exit(1)


mcp = FastMCP("xf-internal-linker")


# ────────────────────────────────────────────────────────────────────
# Tools
# ────────────────────────────────────────────────────────────────────


@mcp.tool()
def get_top_candidates(month: str, n: int = 300) -> list[dict]:
    """Return up to N top-scoring pending link suggestions for the month.

    Used by the Claude Code monthly-top-50 prompt to pull the candidate pool
    before applying editorial rules. KISS v1 ignores `month` and just returns
    the N highest-scoring pending rows; a future refinement can filter by
    `created_at__year_month=month`.
    """
    from apps.pipeline.services import monthly_picker

    candidates = monthly_picker.candidates_from_orm(month=month, top_n=int(n))
    return [
        {
            "suggestion_id": c.suggestion_id,
            "composite_score": round(c.composite_score, 4),
            "source_thread_id": c.source_thread_id,
            "anchor_phrase": c.anchor_phrase,
            "source_post_age_days": c.source_post_age_days,
            "source_title": c.source_title,
            "target_title": c.target_title,
            "target_url": c.target_url,
            "cluster_label": c.cluster_label,
        }
        for c in candidates
    ]


@mcp.tool()
def get_dashboard_metrics() -> dict:
    """One-shot snapshot of the linker's overall health.

    Returns a small JSON-friendly dict with suggestion-status counts and a
    timestamp. AI agents can read this to answer questions like "how many
    pending suggestions are there?" without trawling the whole API.
    """
    from apps.suggestions.models import Suggestion  # type: ignore[import-not-found]

    counts: dict[str, int] = {}
    rows = (
        Suggestion.objects.values("status")
        .order_by()
        .annotate(
            n=__import__("django.db.models", fromlist=["Count"]).Count("suggestion_id")
        )
    )
    for row in rows:
        counts[row["status"]] = row["n"]
    return {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "suggestion_counts_by_status": counts,
        "total": sum(counts.values()),
    }


@mcp.tool()
def list_orphans(limit: int = 25) -> list[dict]:
    """Return content items with zero approved or applied incoming links.

    KISS v1 reads from the existing graph-orphans helper if available; falls
    back to a simple SQL aggregate on the ContentItem table. Useful for
    "tell me which articles need links" prompts.
    """
    try:
        from apps.content.models import ContentItem  # type: ignore[import-not-found]
    except ImportError:
        return []
    qs = (
        ContentItem.objects.annotate(
            inbound=__import__("django.db.models", fromlist=["Count"]).Count(
                "destination_suggestions",
                filter=__import__("django.db.models", fromlist=["Q"]).Q(
                    destination_suggestions__status__in=[
                        "approved",
                        "applied",
                        "verified",
                    ]
                ),
            )
        )
        .filter(inbound=0)
        .order_by("-created_at")[: int(limit)]
    )
    out: list[dict] = []
    for item in qs:
        out.append(
            {
                "id": getattr(item, "id", None),
                "title": getattr(item, "title", None)
                or getattr(item, "name", None)
                or "(untitled)",
                "url": getattr(item, "url", None)
                or getattr(item, "canonical_url", None)
                or "",
            }
        )
    return out


@mcp.tool()
def suggest_links(query: str, limit: int = 25) -> list[dict]:
    """Free-text query against pending Suggestions.

    Looks for `query` (case-insensitive substring match) in the destination
    title, host sentence text, and anchor phrase fields. Useful for prompts
    like "find suggestions about embeddings".
    """
    try:
        from django.db.models import Q
        from apps.suggestions.models import Suggestion  # type: ignore[import-not-found]
    except ImportError:
        return []
    q = (query or "").strip()
    if not q:
        return []
    qs = (
        Suggestion.objects.filter(status="pending")
        .filter(
            Q(destination_title__icontains=q)
            | Q(host_sentence_text__icontains=q)
            | Q(anchor_phrase__icontains=q)
        )
        .order_by("-score_final")[: int(limit)]
    )
    return [_suggestion_summary(s) for s in qs]


@mcp.tool()
def get_review_queue(state: str = "pending", limit: int = 25) -> list[dict]:
    """Return suggestions in the given lifecycle state, newest first.

    `state` defaults to `pending`. Pass `proposed` to see what the monthly
    Top-50 picker has flagged but not yet been human-reviewed.
    """
    try:
        from apps.suggestions.models import Suggestion  # type: ignore[import-not-found]
    except ImportError:
        return []
    valid = {
        "pending",
        "proposed",
        "approved",
        "rejected",
        "applied",
        "verified",
        "stale",
        "superseded",
    }
    if state not in valid:
        return []
    qs = Suggestion.objects.filter(status=state).order_by("-score_final")[: int(limit)]
    return [_suggestion_summary(s) for s in qs]


@mcp.tool()
def search_content(query: str, limit: int = 25) -> list[dict]:
    """Find ContentItems whose title or URL contains `query` (case-insensitive)."""
    try:
        from django.db.models import Q
        from apps.content.models import ContentItem  # type: ignore[import-not-found]
    except ImportError:
        return []
    q = (query or "").strip()
    if not q:
        return []
    qs = ContentItem.objects.filter(
        Q(title__icontains=q) | Q(url__icontains=q)
    ).order_by("-created_at")[: int(limit)]
    return [
        {
            "id": getattr(item, "id", None),
            "title": getattr(item, "title", None) or "(untitled)",
            "url": getattr(item, "url", None)
            or getattr(item, "canonical_url", None)
            or "",
        }
        for item in qs
    ]


@mcp.tool()
def get_link_health() -> dict:
    """One-shot health snapshot for the link graph.

    Returns counts of: approved live links, broken links, orphan content
    items. KISS v1 — straight from the Suggestion + ContentItem tables; no
    fancy graph stats. Useful for "is anything broken?" questions.
    """
    try:
        from django.db.models import Count, Q
        from apps.suggestions.models import Suggestion  # type: ignore[import-not-found]
        from apps.content.models import ContentItem  # type: ignore[import-not-found]
    except ImportError:
        return {"error": "models unavailable"}

    approved_live = Suggestion.objects.filter(
        status__in=["approved", "applied", "verified"]
    ).count()
    broken = Suggestion.objects.filter(status="stale").count()
    orphans = (
        ContentItem.objects.annotate(
            inbound=Count(
                "destination_suggestions",
                filter=Q(
                    destination_suggestions__status__in=[
                        "approved",
                        "applied",
                        "verified",
                    ]
                ),
            )
        )
        .filter(inbound=0)
        .count()
    )
    return {
        "approved_live_links": approved_live,
        "stale_or_broken_links": broken,
        "orphan_content_items": orphans,
    }


@mcp.tool()
def find_semantic_pairs(topic: str = "", limit: int = 25) -> list[dict]:
    """Return session co-occurrence pairs (behavioural hubs).

    Optional `topic` filters by a substring match on either side's title.
    Useful for "which two topics co-navigate together?" prompts.

    Backed by `SessionCoOccurrencePair` — pairs of content items that the
    same GA4 session visited, ranked by `co_session_count`.
    """
    try:
        from django.db.models import Q
        from apps.cooccurrence.models import SessionCoOccurrencePair  # type: ignore[import-not-found]
    except ImportError:
        return []
    qs = SessionCoOccurrencePair.objects.select_related(
        "source_content_item", "dest_content_item"
    )
    topic_q = (topic or "").strip()
    if topic_q:
        qs = qs.filter(
            Q(source_content_item__title__icontains=topic_q)
            | Q(dest_content_item__title__icontains=topic_q)
        )
    qs = qs.order_by("-co_session_count")[: int(limit)]
    return [
        {
            "source_id": getattr(pair.source_content_item, "id", None)
            if pair.source_content_item_id
            else None,
            "source_title": getattr(pair.source_content_item, "title", "")
            or "(untitled)",
            "dest_id": getattr(pair.dest_content_item, "id", None)
            if pair.dest_content_item_id
            else None,
            "dest_title": getattr(pair.dest_content_item, "title", "") or "(untitled)",
            "co_session_count": getattr(pair, "co_session_count", 0),
            "lift": float(getattr(pair, "lift", 0.0) or 0.0),
        }
        for pair in qs
    ]


def _suggestion_summary(s) -> dict:
    """Compact JSON-ready snapshot of one Suggestion."""
    return {
        "suggestion_id": str(s.suggestion_id),
        "status": s.status,
        "score_final": float(s.score_final or 0.0),
        "anchor_phrase": (s.anchor_phrase or "").strip(),
        "destination_title": s.destination_title or "(untitled)",
        "host_sentence_text": (s.host_sentence_text or "")[:200],
    }


def main() -> None:
    """Entry point — runs the MCP server on stdio."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s mcp_server: %(message)s",
        stream=sys.stderr,
    )
    logger.info("starting xf-internal-linker MCP server (stdio transport)")
    mcp.run()  # default transport is stdio


if __name__ == "__main__":
    main()
