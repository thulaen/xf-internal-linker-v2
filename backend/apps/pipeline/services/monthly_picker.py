"""Monthly Top-50 link-suggestion picker.

Pure-Python orchestrator that produces the same `monthly-suggestions-YYYY-MM.md`
report as the Claude Code path, without any LLM dependency. The composite
score is already computed by the existing ranker — this module just applies
the editorial rules and writes a markdown summary.

Editorial rules (per the approved plan):
    1. Diversity: at most 3 suggestions per source thread / source post.
    2. Anchor variety: at most 2 suggestions sharing the same anchor phrase.
    3. Score floor: composite_score >= 0.70.
    4. Freshness bias: rank tie-breaker boosts source posts younger than 90 days.
    5. Pick top 50.

Strategy B (this file) is the always-on fallback. Strategy A (Claude Code)
calls the same DB rows via MCP tools but uses an LLM to apply roughly the
same editorial rules. Either way the report file path and the database
`status='proposed'` flagging are identical so downstream surfaces don't care.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Tunable defaults (kept module-level so unit tests can override).
DEFAULT_TOP_N_CANDIDATES = 300
DEFAULT_PICK_LIMIT = 50
DEFAULT_PER_SOURCE_CAP = 3
DEFAULT_PER_ANCHOR_CAP = 2
DEFAULT_SCORE_FLOOR = 0.70
DEFAULT_FRESHNESS_DAYS = 90


@dataclass(frozen=True)
class Candidate:
    """Minimal pick-input shape — easy to hand-build in tests.

    Production callers map a Suggestion ORM row + its source-content metadata
    onto this dataclass via `candidates_from_orm()`. Tests pass dicts directly.
    The `suggestion_id` is a string (the Suggestion model uses UUID) so
    callers don't have to think about UUID vs int.
    """

    suggestion_id: str
    composite_score: float
    source_thread_id: str
    anchor_phrase: str
    source_post_age_days: int
    source_title: str
    target_title: str
    target_url: str
    cluster_label: str = "uncategorised"


@dataclass(frozen=True)
class PickResult:
    """One picked suggestion + the plain-English explanation we render."""

    candidate: Candidate
    why: str


def _explain(c: Candidate) -> str:
    """Pure-template explanation when no LLM is available.

    Avoids LLM dependency for KISS. The score breakdown is more honest than
    a hallucinated reason, and reads naturally enough for an operator.
    """
    score_pct = int(round(c.composite_score * 100))
    parts = [f"Score {score_pct}/100"]
    if c.source_post_age_days <= DEFAULT_FRESHNESS_DAYS:
        parts.append(f"fresh source ({c.source_post_age_days} days old)")
    else:
        parts.append(f"older source ({c.source_post_age_days} days)")
    parts.append(f'anchor "{c.anchor_phrase}"')
    return " · ".join(parts) + "."


def pick_top(
    candidates: Iterable[Candidate],
    *,
    limit: int = DEFAULT_PICK_LIMIT,
    per_source_cap: int = DEFAULT_PER_SOURCE_CAP,
    per_anchor_cap: int = DEFAULT_PER_ANCHOR_CAP,
    score_floor: float = DEFAULT_SCORE_FLOOR,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> list[PickResult]:
    """Apply the editorial rules and return up to `limit` picks."""
    # Sort by composite score descending; ties broken by freshness.
    pool = sorted(
        (c for c in candidates if c.composite_score >= score_floor),
        key=lambda c: (
            -c.composite_score,
            0 if c.source_post_age_days <= freshness_days else 1,
            c.suggestion_id,
        ),
    )
    by_source: dict[str, int] = defaultdict(int)
    by_anchor: dict[str, int] = defaultdict(int)
    picks: list[PickResult] = []
    for c in pool:
        if len(picks) >= limit:
            break
        if by_source[c.source_thread_id] >= per_source_cap:
            continue
        anchor_key = c.anchor_phrase.strip().lower()
        if by_anchor[anchor_key] >= per_anchor_cap:
            continue
        picks.append(PickResult(candidate=c, why=_explain(c)))
        by_source[c.source_thread_id] += 1
        by_anchor[anchor_key] += 1
    return picks


def render_markdown_report(month: str, picks: list[PickResult]) -> str:
    """Render the `docs/reports/monthly-suggestions-YYYY-MM.md` body."""
    if not picks:
        return (
            f"# Monthly link suggestions — {month}\n\n"
            "No picks this month — every candidate was below the score floor.\n"
        )
    grouped: dict[str, list[PickResult]] = defaultdict(list)
    for p in picks:
        grouped[p.candidate.cluster_label].append(p)
    lines: list[str] = [
        f"# Monthly link suggestions — {month}",
        "",
        f"_{len(picks)} picks chosen automatically. Review each pick before pasting "
        "the anchor text into XenForo._",
        "",
    ]
    for cluster, cluster_picks in sorted(grouped.items()):
        lines.append(f"## {cluster}  ({len(cluster_picks)})")
        lines.append("")
        for p in cluster_picks:
            c = p.candidate
            lines.append(f"- **{c.source_title}** → [{c.target_title}]({c.target_url})")
            lines.append(f"  - Anchor: `{c.anchor_phrase}`")
            lines.append(f"  - {p.why}")
        lines.append("")
    lines.append("---")
    lines.append(
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_"
    )
    return "\n".join(lines) + "\n"


def candidates_from_orm(
    month: str, top_n: int = DEFAULT_TOP_N_CANDIDATES
) -> list[Candidate]:
    """Pull top-N pending Suggestion rows mapped to Candidate.

    Reads only fields that exist on the Suggestion model in this codebase
    (score_final as the composite score, anchor_phrase, destination_title
    denormalised, host FK for the source thread). Imports are inline so
    the module is import-safe in SimpleTestCase contexts.

    `month` is currently unused for filtering — we take the top-N pending
    suggestions at the moment the job runs. A future refinement could
    filter by `created_at__year_month=month` once the operator wants
    strictly per-month batches; for v1 the AI uses whatever's pending.
    """
    from apps.suggestions.models import Suggestion  # type: ignore[import-not-found]

    qs = (
        Suggestion.objects.filter(status="pending")
        .select_related("host", "destination")
        .order_by("-score_final")[:top_n]
    )
    now = datetime.now(timezone.utc)
    out: list[Candidate] = []
    for s in qs:
        host = getattr(s, "host", None)
        destination = getattr(s, "destination", None)
        host_id = getattr(host, "id", None) or getattr(host, "pk", None)
        host_title = (
            getattr(host, "title", None)
            or getattr(host, "name", None)
            or s.host_sentence_text[:80]
            or "Source"
        )
        host_created = getattr(host, "created_at", None)
        age_days = 9_999
        if isinstance(host_created, datetime):
            age_days = max(0, (now - host_created).days)
        target_url = (
            getattr(destination, "url", None)
            or getattr(destination, "canonical_url", None)
            or ""
        )
        cluster_label = "uncategorised"
        diag = getattr(s, "cluster_diagnostics", None)
        if isinstance(diag, dict):
            cluster_label = str(
                diag.get("cluster_label") or diag.get("cluster") or cluster_label
            )
        out.append(
            Candidate(
                suggestion_id=str(s.suggestion_id),
                composite_score=float(s.score_final or 0.0),
                source_thread_id=str(host_id or "unknown"),
                anchor_phrase=(s.anchor_phrase or "").strip(),
                source_post_age_days=age_days,
                source_title=str(host_title),
                target_title=str(s.destination_title or "Target"),
                target_url=str(target_url),
                cluster_label=cluster_label,
            )
        )
    return out


def run_python_strategy(
    month: str,
    *,
    output_root: Optional[Path] = None,
    pick_limit: int = DEFAULT_PICK_LIMIT,
) -> Path:
    """End-to-end Strategy B run: load → pick → write report → flag DB.

    Returns the path of the markdown report written to disk.
    """
    candidates = candidates_from_orm(month)
    picks = pick_top(candidates, limit=pick_limit)
    report_dir = output_root or _default_report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"monthly-suggestions-{month}.md"
    report_path.write_text(render_markdown_report(month, picks), encoding="utf-8")
    _flag_proposed(picks, batch_label=month)
    logger.info("monthly_picker: wrote %s with %d picks", report_path, len(picks))
    return report_path


def _flag_proposed(picks: list[PickResult], *, batch_label: str) -> None:
    """Mark each chosen suggestion as 'proposed' + stamp the batch label.

    Migration `suggestions/0065_add_batch_label` introduces both the
    `'proposed'` status choice and the `batch_label` CharField. A single
    bulk update is used because at 50 rows per call it's much cheaper than
    per-row save() — and it stays atomic if a transaction is wrapped around
    the caller.
    """
    if not picks:
        return
    try:
        from apps.suggestions.models import Suggestion  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "monthly_picker: Suggestion model not importable; skipping DB flagging"
        )
        return
    ids = [p.candidate.suggestion_id for p in picks]
    updated = Suggestion.objects.filter(suggestion_id__in=ids).update(
        status="proposed",
        batch_label=batch_label,
    )
    logger.info(
        "monthly_picker: flagged %d suggestion(s) as proposed (batch=%s)",
        updated,
        batch_label,
    )


def _default_report_dir() -> Path:
    """`<repo>/docs/reports/` resolved from this file's location."""
    here = Path(__file__).resolve()
    # apps/pipeline/services/monthly_picker.py → up 4 levels to repo root
    return here.parents[4] / "docs" / "reports"
