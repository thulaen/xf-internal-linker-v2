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
        .annotate(n=__import__("django.db.models", fromlist=["Count"]).Count("suggestion_id"))
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
                    destination_suggestions__status__in=["approved", "applied", "verified"]
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
                "title": getattr(item, "title", None) or getattr(item, "name", None) or "(untitled)",
                "url": getattr(item, "url", None) or getattr(item, "canonical_url", None) or "",
            }
        )
    return out


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
