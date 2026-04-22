"""
Phase MS — Meta-algorithm registry.

Single source of truth for the Meta Algorithm Settings tab. Enumerates
every meta-algorithm the app knows about (today: 210 forward-declared
+ 39 active = 249 total), derives metadata by parsing the existing
`recommended_weights_phase2_metas_*.py` files so a new block auto-
surfaces without anyone touching this file.

Design rule: NO new data store. The registry reads:
  * the `FORWARD_DECLARED_WEIGHTS_PHASE2_*` dicts (already the canonical
    list of prefixes + default values)
  * per-line comments in the source files to lift `META-NN — Title` and
    `Block PX —` headers into machine-readable metadata
  * `AppSetting` rows at runtime for current on/off state + weights

A handful of active metas (META-01..META-39) are not in the forward-
declared files because they're already wired into production. Those
are listed explicitly in `_ACTIVE_METAS`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable


# ─────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MetaDefinition:
    """One meta-algorithm entry the Settings tab renders."""

    id: str  # stable short id, e.g. "newton"
    meta_code: str  # canonical code, e.g. "META-40"
    family: str  # "P1", "P2", ..., "Q24", or "active"
    title: str  # human-readable headline
    status: str  # "active" | "forward-declared" | "disabled"
    weight_key: str | None  # e.g. "newton.ranking_weight" when present
    enabled_key: str  # e.g. "newton.enabled"
    spec_path: str | None  # docs/specs/meta-NN-*.md when inferable
    cpp_kernel: str | None  # e.g. "pagerank.pagerank_step"
    # Raw hyper-parameter keys owned by this meta (for future deep-edit UI).
    param_keys: tuple[str, ...] = field(default_factory=tuple)


# ─────────────────────────────────────────────────────────────────────
# The 39 active metas (META-01..META-39)
# ─────────────────────────────────────────────────────────────────────
#
# These are currently-running meta-algorithms. They don't need a
# forward-declared dict because they're already baked into the pipeline.
# The `family: "active"` tag groups them under a single Active chip in
# the UI so noobs can filter to what's actually doing work.

_ACTIVE_METAS: tuple[dict, ...] = (
    {"id": "sgd", "meta_code": "META-01", "title": "SGD — first-order baseline"},
    {"id": "momentum", "meta_code": "META-02", "title": "Momentum (Polyak)"},
    {"id": "adagrad", "meta_code": "META-03", "title": "AdaGrad"},
    {"id": "rmsprop", "meta_code": "META-04", "title": "RMSprop"},
    {"id": "adam", "meta_code": "META-34", "title": "Adam (Kingma & Ba 2014)"},
    {"id": "bge_m3", "meta_code": "META-05", "title": "BGE-M3 sentence embeddings"},
    {
        "id": "pagerank",
        "meta_code": "META-06",
        "title": "PageRank authority",
        "cpp_kernel": "pagerank.pagerank_step",
    },
    {
        "id": "simsearch",
        "meta_code": "META-07",
        "title": "Cosine sim top-k",
        "cpp_kernel": "simsearch.score_and_topk",
    },
    {
        "id": "texttok",
        "meta_code": "META-08",
        "title": "Tokeniser",
        "cpp_kernel": "texttok.tokenize_text_batch",
    },
    {"id": "bm25", "meta_code": "META-09", "title": "BM25 lexical ranking"},
    {"id": "tfidf", "meta_code": "META-10", "title": "TF-IDF baseline"},
    {"id": "jaccard", "meta_code": "META-11", "title": "Keyword Jaccard"},
    {"id": "cosine_similarity", "meta_code": "META-12", "title": "Cosine similarity"},
    {"id": "slate_diversity", "meta_code": "META-13", "title": "Slate diversity (MMR)"},
    {
        "id": "feedrerank",
        "meta_code": "META-14",
        "title": "Feedback reranker",
        "cpp_kernel": "feedrerank.rerank",
    },
    {"id": "link_freshness", "meta_code": "META-15", "title": "Link freshness decay"},
    {"id": "click_distance", "meta_code": "META-16", "title": "Click distance"},
    {
        "id": "weighted_authority",
        "meta_code": "META-17",
        "title": "Weighted destination authority",
    },
    {"id": "phrase_match", "meta_code": "META-18", "title": "Phrase match"},
    {"id": "node_proximity", "meta_code": "META-19", "title": "Scope tree proximity"},
    {"id": "post_quality", "meta_code": "META-20", "title": "Host post quality"},
    {"id": "learned_anchor", "meta_code": "META-21", "title": "Learned anchor"},
    {"id": "rare_term", "meta_code": "META-22", "title": "Rare-term propagation"},
    {
        "id": "field_aware_relevance",
        "meta_code": "META-23",
        "title": "Field-aware relevance",
    },
    {
        "id": "feedback_rerank",
        "meta_code": "META-24",
        "title": "Feedback reranker (Py)",
    },
    {"id": "spam_guard", "meta_code": "META-25", "title": "Spam guard"},
    {"id": "value_model", "meta_code": "META-26", "title": "Value model"},
    {"id": "cooccurrence", "meta_code": "META-27", "title": "Session cooccurrence"},
    {"id": "behavioral_hubs", "meta_code": "META-28", "title": "Behavioral hubs"},
    {"id": "knowledge_graph", "meta_code": "META-29", "title": "Knowledge graph"},
    {"id": "attribution", "meta_code": "META-30", "title": "Attribution engine"},
    {"id": "weight_tuner", "meta_code": "META-31", "title": "Weight tuner (monthly)"},
    {"id": "impact_engine", "meta_code": "META-32", "title": "Impact engine"},
    {"id": "crawler_discovery", "meta_code": "META-33", "title": "Crawler discovery"},
    # META-34 Adam already listed above.
    {"id": "ranking_challenger", "meta_code": "META-35", "title": "Ranking challenger"},
    {"id": "explore_exploit", "meta_code": "META-36", "title": "Explore/exploit"},
    {"id": "silo_guard", "meta_code": "META-37", "title": "Silo leakage guard"},
    {"id": "clustering", "meta_code": "META-38", "title": "Near-duplicate clustering"},
    {"id": "graph_candidate", "meta_code": "META-39", "title": "Graph candidate"},
)


# ─────────────────────────────────────────────────────────────────────
# Source-file parsing for the forward-declared blocks
# ─────────────────────────────────────────────────────────────────────


# File → family range. Pending Phase-2 meta weight files were removed per
# PR-A slice 5 — the 52-pick roster gets fresh specs/weights in later PRs.
_FILE_TO_FAMILY_RANGE: dict[str, tuple[str, ...]] = {}

_META_COMMENT_RE = re.compile(
    r"""^\s*\#\s*META-(?P<num>\d+)\s*[—\-]\s*(?P<title>[^\[\(]+)""",
    re.MULTILINE,
)
_BLOCK_HEADER_RE = re.compile(
    r"""^\s*\#\s*(?:BLOCK\s+|Block\s+)(?P<family>[PQ]\d+)\b""",
    re.MULTILINE | re.IGNORECASE,
)
_ENABLED_KEY_RE = re.compile(
    r'^\s*"(?P<prefix>[a-z][a-z0-9_]*)\.enabled"\s*:',
    re.MULTILINE,
)


@dataclass
class _ParsedMeta:
    prefix: str  # e.g. "newton"
    meta_code: str  # e.g. "META-40"
    title: str
    family: str  # "P1"
    enabled_line_no: int


def _parse_meta_file(path: Path) -> list[_ParsedMeta]:
    """Walk a single `recommended_weights_phase2_*.py` file.

    For each `"<prefix>.enabled"` line, walk upward (in source order) to
    find the nearest preceding `# META-NN — Title` comment and the
    nearest `# Block PX —` header. Returns one record per prefix.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Pre-compute position of every META-NN comment + every Block header
    # by line number.
    meta_positions: list[tuple[int, str, str]] = []  # (line_no, meta_code, title)
    block_positions: list[tuple[int, str]] = []  # (line_no, family)

    for idx, line in enumerate(lines):
        m = _META_COMMENT_RE.match(line + "\n")
        if m:
            meta_positions.append(
                (
                    idx,
                    f"META-{m.group('num').zfill(2)}",
                    m.group("title").strip(" .").strip(),
                )
            )
            continue
        b = _BLOCK_HEADER_RE.match(line + "\n")
        if b:
            block_positions.append((idx, b.group("family").upper()))

    out: list[_ParsedMeta] = []
    seen_prefixes: set[str] = set()
    for idx, line in enumerate(lines):
        e = _ENABLED_KEY_RE.match(line + "\n")
        if not e:
            continue
        prefix = e.group("prefix")
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)

        # Nearest META comment at or before this line.
        meta_code = ""
        title = prefix.replace("_", " ").title()
        for m_line, m_code, m_title in reversed(meta_positions):
            if m_line <= idx:
                meta_code = m_code
                title = m_title
                break

        # Nearest Block header at or before this line.
        family = ""
        for b_line, b_family in reversed(block_positions):
            if b_line <= idx:
                family = b_family
                break

        out.append(
            _ParsedMeta(
                prefix=prefix,
                meta_code=meta_code,
                title=title,
                family=family or "Unspecified",
                enabled_line_no=idx,
            )
        )

    return out


@lru_cache(maxsize=1)
def _all_parsed_metas() -> tuple[_ParsedMeta, ...]:
    """Load + parse every known weight file once."""
    base = Path(__file__).resolve().parent
    out: list[_ParsedMeta] = []
    for filename in _FILE_TO_FAMILY_RANGE:
        path = base / filename
        if path.exists():
            out.extend(_parse_meta_file(path))
    return tuple(out)


# ─────────────────────────────────────────────────────────────────────
# Public API — the view layer consumes these helpers.
# ─────────────────────────────────────────────────────────────────────


def _spec_path_for(meta_code: str) -> str | None:
    """Canonical spec filename — returns string, existence not verified."""
    if not meta_code or not meta_code.startswith("META-"):
        return None
    # `docs/specs/meta-40-lbfgs-b.md` style; we only know the number here,
    # so return the fuzzy prefix the frontend can glob-link to.
    num = meta_code.split("-", 1)[1].lstrip("0") or "0"
    return f"docs/specs/meta-{num.zfill(2)}-*.md"


def _params_for(prefix: str) -> tuple[str, ...]:
    """All AppSetting-shaped keys starting with `<prefix>.`."""
    from .recommended_weights import RECOMMENDED_PRESET_WEIGHTS

    return tuple(
        k
        for k in sorted(RECOMMENDED_PRESET_WEIGHTS.keys())
        if k.startswith(f"{prefix}.")
    )


def enumerate_metas() -> list[MetaDefinition]:
    """Return the full list the Settings tab renders.

    Order: active metas first (sorted by META-NN), then forward-declared
    in the natural reading order of the source files (so adjacent blocks
    stay together in the virtual-scroll list).
    """
    out: list[MetaDefinition] = []

    # Active metas (META-01..META-39). `status='active'` and family='active'.
    for entry in _ACTIVE_METAS:
        prefix = entry["id"]
        out.append(
            MetaDefinition(
                id=prefix,
                meta_code=entry["meta_code"],
                family="active",
                title=entry["title"],
                status="active",
                weight_key=f"{prefix}.ranking_weight"
                if _has_weight_key(prefix)
                else None,
                enabled_key=f"{prefix}.enabled",
                spec_path=_spec_path_for(entry["meta_code"]),
                cpp_kernel=entry.get("cpp_kernel"),
                param_keys=_params_for(prefix),
            )
        )

    # Forward-declared + signals.
    for parsed in _all_parsed_metas():
        out.append(
            MetaDefinition(
                id=parsed.prefix,
                meta_code=parsed.meta_code,
                family=parsed.family,
                title=parsed.title,
                status="forward-declared",
                weight_key=f"{parsed.prefix}.ranking_weight"
                if _has_weight_key(parsed.prefix)
                else None,
                enabled_key=f"{parsed.prefix}.enabled",
                spec_path=_spec_path_for(parsed.meta_code),
                cpp_kernel=None,
                param_keys=_params_for(parsed.prefix),
            )
        )

    return out


def _has_weight_key(prefix: str) -> bool:
    try:
        from .recommended_weights import RECOMMENDED_PRESET_WEIGHTS
    except Exception:  # noqa: BLE001 — import cycles during app boot
        return False
    return f"{prefix}.ranking_weight" in RECOMMENDED_PRESET_WEIGHTS


def families_summary(metas: Iterable[MetaDefinition]) -> list[dict]:
    """Count of metas per family, used for the chip labels.

    Returns list of dicts `{family, total, active, disabled, forward}`.
    """
    buckets: dict[str, dict[str, int]] = {}
    for m in metas:
        fam = m.family
        b = buckets.setdefault(
            fam, {"family": fam, "total": 0, "active": 0, "disabled": 0, "forward": 0}
        )
        b["total"] += 1
        if m.status == "active":
            b["active"] += 1
        elif m.status == "disabled":
            b["disabled"] += 1
        elif m.status == "forward-declared":
            b["forward"] += 1

    # Stable order: active → P1..P12 → Q1..Q24 → signal → others alphabetically.
    def sort_key(bucket: dict) -> tuple:
        fam = bucket["family"]
        if fam == "active":
            return (0, 0)
        if fam.startswith("P"):
            try:
                return (1, int(fam[1:]))
            except ValueError:
                return (1, 999)
        if fam.startswith("Q"):
            try:
                return (2, int(fam[1:]))
            except ValueError:
                return (2, 999)
        if fam == "signal":
            return (3, 0)
        return (4, fam)

    return sorted(buckets.values(), key=sort_key)


__all__ = [
    "MetaDefinition",
    "enumerate_metas",
    "families_summary",
]
