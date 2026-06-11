"""Canonical registry of every tunable AppSetting key.

Single source of truth for:
  - the meta-algorithm autotuner (FR-018b) — reads ``META_PARAMS``
  - the ranking-weight autotuner (FR-018) — reads ``BLEND_WEIGHTS``
  - the two pre-commit hooks ``check-autotuner-registry.py`` and
    ``check-recommended-preset-coverage.py`` — read this file's TUNABLE
    KEYSET to decide whether a new ``AppSetting.key`` migration violates
    the future-awareness rule from ``docs/AUTOTUNER-FUTURE-AWARENESS.md``.

When you add a new ranking weight or meta-algorithm parameter, ADD ONE
ENTRY HERE in the correct dict. The autotuner picks it up automatically
on its next run; the hooks unblock the commit. Without an entry — and
without an explicit ``# AUTOTUNER-EXCLUDED: <reason>`` comment in the
introducing migration — the commit fails.

Schema (both dicts):
    key: str -> TunableEntry(
        lower: float,
        upper: float,
        default: str,           # string value the AppSetting row stores
        citation: str,          # paper / RFC / patent the bounds came from
    )

Lower bound MUST be strictly positive (DEFAULT-ON-RULE.md).

The two dicts are kept separate because:
  - BLEND_WEIGHTS sum to 1.0 (simplex constraint enforced by WeightTuner)
  - META_PARAMS are independent (bound-constrained per-key)
The autotuner code chooses the right strategy per-dict.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TunableEntry:
    """One entry in either META_PARAMS or BLEND_WEIGHTS.

    ``lower`` and ``upper`` are float bounds the autotuner clamps every
    proposal into. ``default`` is the string value seeded into AppSetting
    on a fresh install. ``citation`` is the published source of the
    bounds (DOI / RFC / patent / stable URL) per CITATION-RULE.md.
    """

    lower: float
    upper: float
    default: str
    citation: str


# ── Meta-algorithm parameters (FR-018b) ─────────────────────────────
#
# These are independent knobs the meta-algo tuner clamps per-key.
# Bounds copied verbatim from `meta_tuner._META_PARAM_BOUNDS` to preserve
# behaviour byte-for-byte; defaults sourced from
# `recommended_weights.RECOMMENDED_PRESET_WEIGHTS`.
META_PARAMS: dict[str, TunableEntry] = {
    "graph.nk_link_prediction.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - Liben-Nowell & Kleinberg 2007",
    ),
    "graph.nk_communities.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - Blondel et al. 2008",
    ),
    "graph.nk_betweenness.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - Brandes 2001",
    ),
    "graph.nk_reach.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - Reach proxy",
    ),
    "graph.nk_centrality.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - Bonacich 1972",
    ),
    "graph.nk_kcore.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - Seidman 1983",
    ),
    "graph.nk_components.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - Connected Components",
    ),
    "graph.nk_local_clustering.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - Clustering",
    ),
    "graph.nk_node2vec.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - node2vec Grover & Leskovec 2016",
    ),
    "graph.nk_group_seed_rank.ranking_weight": TunableEntry(
        lower=0.01, upper=1.0, default="0.05",
        citation="FR-networkit-graph-signals - Group closeness",
    ),

    "pipeline.rrf_k": TunableEntry(
        lower=20.0, upper=200.0, default="60",
        citation="Cormack et al. 2009 SIGIR'09 §3 (k=60 default; range 20–200)",
    ),
    "pipeline.bm25_k1": TunableEntry(
        lower=0.5, upper=3.0, default="1.2",
        citation="Robertson & Zaragoza 2009 F&T in IR §3.5 (k1 ∈ [0.5, 3.0])",
    ),
    "pipeline.bm25_b": TunableEntry(
        lower=0.05, upper=1.0, default="0.75",
        citation="Robertson & Zaragoza 2009 §3.5 (b ∈ [0.05, 1.0])",
    ),
    "pipeline.stage1_mmr_lambda": TunableEntry(
        lower=0.05, upper=0.95, default="0.65",
        citation="Carbonell & Goldstein 1998 SIGIR §3 (lambda ∈ [0, 1])",
    ),
    "slate_diversity.similarity_cap": TunableEntry(
        lower=0.5, upper=1.0, default="0.90",
        citation="Drosou & Pitoura 2010 §3.1 (similarity cap typically 0.5–1.0)",
    ),
    "slate_diversity.diversity_lambda": TunableEntry(
        lower=0.05, upper=0.95, default="0.65",
        citation="Carbonell & Goldstein 1998 §3 (lambda ∈ [0, 1])",
    ),
    "pipeline.stage1_top_k": TunableEntry(
        lower=10.0, upper=500.0, default="200",
        citation="Operator-tunable retrieval depth — see docs/PERFORMANCE.md §3",
    ),
    "pipeline.stage2_top_k": TunableEntry(
        lower=1.0, upper=100.0, default="20",
        citation="Operator-tunable retrieval depth — see docs/PERFORMANCE.md §3",
    ),
    "pipeline.stage1_overfetch_multiplier": TunableEntry(
        lower=1.0, upper=5.0, default="1.5",
        citation="Empirical — overfetch absorbs filtering at later stages without bloating Stage-1 RAM",
    ),
    "pipeline.min_semantic_score": TunableEntry(
        lower=0.10, upper=0.50, default="0.20",
        citation="Anti-noise threshold; matches recommended_weights.py default",
    ),
    "pipeline.nrt_delta_max_size": TunableEntry(
        lower=1000.0, upper=100000.0, default="10000",
        citation="NRT delta buffer ceiling — bounded so the delta merge stays O(1)",
    ),
    "pipeline.nrt_delta_refresh_seconds": TunableEntry(
        lower=10.0, upper=300.0, default="60",
        citation="NRT delta refresh cadence",
    ),
    "pipeline.calibration_validation_set_min_size": TunableEntry(
        lower=100.0, upper=10000.0, default="500",
        citation="Calibration validation floor — Bishop 2006 §3.1.5 (split-sample)",
    ),
    "click_distance.k_cd": TunableEntry(
        lower=1.0, upper=10.0, default="4.0",
        citation="FR-012 click-distance decay (Liu et al. 2009 LtR §1.5)",
    ),
    "explore_exploit.exploration_rate": TunableEntry(
        lower=0.1, upper=3.0, default="1.41421356237",
        citation="Auer et al. 2002 Machine Learning §4 (UCB1 exploration constant √2)",
    ),
    "field_aware_relevance.title_field_weight": TunableEntry(
        lower=0.05, upper=1.0, default="0.30",
        citation="Robertson et al. 2004 SIGIR §4 (BM25F field weight ranges)",
    ),
    "field_aware_relevance.heading_field_weight": TunableEntry(
        lower=0.05,
        upper=1.0,
        default="0.15",
        citation="US11328114B2 / US20180276220A1 early rendered-text weighting",
    ),
    "field_aware_relevance.intro_field_weight": TunableEntry(
        lower=0.05,
        upper=1.0,
        default="0.20",
        citation="US11328114B2 / US20180276220A1 early rendered-text weighting",
    ),
    "field_aware_relevance.body_field_weight": TunableEntry(
        lower=0.05,
        upper=1.0,
        default="0.15",
        citation="Robertson et al. 2004 SIGIR field-weight ranges",
    ),
    "field_aware_relevance.scope_field_weight": TunableEntry(
        lower=0.05,
        upper=1.0,
        default="0.10",
        citation="Robertson et al. 2004 SIGIR field-weight ranges",
    ),
    "field_aware_relevance.learned_anchor_field_weight": TunableEntry(
        lower=0.05,
        upper=1.0,
        default="0.10",
        citation="Robertson et al. 2004 SIGIR field-weight ranges",
    ),
    "clustering.similarity_threshold": TunableEntry(
        lower=0.01, upper=0.50, default="0.04",
        citation="FR-014 near-duplicate threshold — Broder 1997 §4 (Jaccard sketch)",
    ),
    "pipeline.embedding_block_size": TunableEntry(
        lower=32.0, upper=1024.0, default="256",
        citation="Hardware-aware block size — adjusts per-tier per docs/PERFORMANCE.md",
    ),
}

# Meta-keys that legitimately live in the Recommended preset but must
# NOT be auto-tuned. Each entry is `key -> reason`. The autotuner reads
# this; the two pre-commit hooks accept these via the
# `# AUTOTUNER-EXCLUDED: <reason>` migration comment.
META_PARAMS_EXCLUDED: dict[str, str] = {
    "pipeline.embedding_age_half_life_days": (
        "data-driven decay constant — depends on actual ingest cadence"
    ),
}


# ── Ranking-blend weights (FR-018 + FR-249) ─────────────────────────
#
# These sum to 1.0 — the WeightTuner enforces a simplex constraint on
# every proposal. Adding a new entry here automatically extends the
# tuner's optimisation surface (it walks BLEND_WEIGHTS keys at __init__
# time instead of the hard-coded 4-list it used pre-2026-05-09).
BLEND_WEIGHTS: dict[str, TunableEntry] = {
    "w_semantic": TunableEntry(
        lower=0.01, upper=0.99, default="0.40",
        citation="FR-018 baseline blend — Liu 2009 §1.5.4 (learning-to-rank composite)",
    ),
    "w_keyword": TunableEntry(
        lower=0.01, upper=0.99, default="0.25",
        citation="FR-018 baseline blend — Robertson & Zaragoza 2009 BM25 contribution",
    ),
    "w_node": TunableEntry(
        lower=0.01, upper=0.99, default="0.20",
        citation="FR-018 baseline blend — graph-based node-affinity contribution",
    ),
    "w_quality": TunableEntry(
        lower=0.01, upper=0.99, default="0.15",
        citation="FR-018 baseline blend — content-quality contribution",
    ),
}

# Conditional blend weights — added to BLEND_WEIGHTS only when their
# enabling AppSetting is non-zero. FR-249 is the canonical example:
# `pipeline.embedding_age_weight_in_composite` gates whether
# `score_embedding_age` participates in the blend.
CONDITIONAL_BLEND_WEIGHTS: dict[str, tuple[str, TunableEntry]] = {
    "w_embedding_age": (
        "pipeline.embedding_age_weight_in_composite",
        TunableEntry(
            lower=0.01, upper=0.99, default="0.05",
            citation="FR-249 embedding-age decay — Lavrenko & Croft 2001 (relevance with time decay)",
        ),
    ),
}


# ── Public helpers (used by autotuners + hooks) ─────────────────────


def get_meta_param_bounds() -> dict[str, tuple[float, float]]:
    """Return the bounds dict in the legacy ``key -> (lo, hi)`` shape."""
    return {k: (v.lower, v.upper) for k, v in META_PARAMS.items()}


def get_meta_param_defaults() -> dict[str, str]:
    """Return the default-value dict in the AppSetting shape."""
    return {k: v.default for k, v in META_PARAMS.items()}


def get_blend_weight_keys() -> list[str]:
    """Return the unconditional blend-weight keys (4 today)."""
    return list(BLEND_WEIGHTS.keys())


def is_tunable_key(key: str) -> bool:
    """True if ``key`` is one of the registered tunable AppSetting keys.

    Used by the pre-commit hooks to decide which migrations to police.
    """
    return key in META_PARAMS or key in BLEND_WEIGHTS or key in {
        ck for ck, _ in CONDITIONAL_BLEND_WEIGHTS.values()
    } or key in {
        cw for cw in CONDITIONAL_BLEND_WEIGHTS.keys()
    }


__all__ = [
    "TunableEntry",
    "META_PARAMS",
    "META_PARAMS_EXCLUDED",
    "BLEND_WEIGHTS",
    "CONDITIONAL_BLEND_WEIGHTS",
    "get_meta_param_bounds",
    "get_meta_param_defaults",
    "get_blend_weight_keys",
    "is_tunable_key",
]
