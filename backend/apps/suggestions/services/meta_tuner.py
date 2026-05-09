"""FR-018b — Meta-algorithm autotuner.

Companion to ``WeightTuner`` (FR-018) that adjusts the *meta-algorithm
parameters* — RRF k, BM25 k1/b, MMR lambda, similarity caps, top-K
knobs — instead of the four ranking-blend weights.

Key differences from WeightTuner
--------------------------------
- **No simplex constraint.** Meta parameters are independent (RRF k
  doesn't have to sum with anything); the optimisation is bound-
  constrained per-key, not constrained-to-sum-to-1.
- **Per-key bounds with explicit floors.** Every lower bound is
  positive and >= a per-key floor — per ``DEFAULT-ON-RULE.md`` the
  tuner cannot disable a meta-algorithm by zeroing its parameter.
- **Drift-limited per run.** Same ±5% drift rule as WeightTuner so a
  single monthly tuning can't move a knob from 60 → 200 in one go.
- **Same challenger escrow + SPRT gate + rollback watchdog.** Wires
  through the same ``RankingChallenger`` model with ``kind="meta_algorithm"``
  so the audit trail is distinct.

References
----------
- BM25 — Robertson & Zaragoza (2009), F&T in IR 3(4) §3.5 (k1, b ranges).
- RRF — Cormack et al. (2009) SIGIR'09 §3 (k = 60 default; range 20–200).
- MMR — Carbonell & Goldstein (1998) SIGIR §3 (lambda 0–1).
- Drift bound (±5%) — same constant as FR-018 (per docs/specs/fr018-auto-tuned-ranking-weights.md).
"""

from __future__ import annotations

import logging
from typing import Mapping

import numpy as np

from apps.suggestions.weight_preset_service import get_current_weights

logger = logging.getLogger(__name__)

# Per-run drift cap (±5%). Same risk profile as WeightTuner.
_META_DRIFT_PCT = 0.05

# Per-key bounds. Every lower bound is positive — DEFAULT-ON-RULE.md
# forbids zeroing a feature. Lower / upper sourced from the citations
# at module top; the comment on each row says where the range comes from.
_META_PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    # Cormack 2009 §3: k=60 is recommended; range 20–200 is safe per the paper.
    "pipeline.rrf_k": (20.0, 200.0),
    # Robertson & Zaragoza 2009 §3.5: k1 ∈ [0.5, 3.0], b ∈ [0.05, 1.0].
    "pipeline.bm25_k1": (0.5, 3.0),
    "pipeline.bm25_b": (0.05, 1.0),
    # Carbonell 1998 §3: lambda ∈ [0, 1]; 0.05 floor avoids "all relevance, no diversity".
    "pipeline.stage1_mmr_lambda": (0.05, 0.95),
    # Drosou & Pitoura 2010 §3.1: similarity cap typically 0.5–1.0.
    "slate_diversity.similarity_cap": (0.5, 1.0),
    "slate_diversity.diversity_lambda": (0.05, 0.95),
    # Stage-1 / Stage-2 top-K — operator-tunable retrieval depth.
    "pipeline.stage1_top_k": (10.0, 500.0),
    "pipeline.stage2_top_k": (1.0, 100.0),
    "pipeline.stage1_overfetch_multiplier": (1.0, 5.0),
    # Min semantic score floor — anti-noise threshold.
    "pipeline.min_semantic_score": (0.10, 0.50),
    # NRT delta refresh / buffer.
    "pipeline.nrt_delta_max_size": (1000.0, 100000.0),
    "pipeline.nrt_delta_refresh_seconds": (10.0, 300.0),
    # Calibration validation set floor.
    "pipeline.calibration_validation_set_min_size": (100.0, 10000.0),
    # Click-distance decay constant (FR-012).
    "click_distance.k_cd": (1.0, 10.0),
    # FR-013 explore-exploit rate (UCB1 exploration constant).
    "explore_exploit.exploration_rate": (0.1, 3.0),
    # Field-aware relevance (FR-011) — title-vs-body weights.
    "field_aware_relevance.title_field_weight": (0.05, 1.0),
    # Clustering similarity threshold (FR-014).
    "clustering.similarity_threshold": (0.01, 0.50),
    # Embedding block size (F2 fix) — autotuner can adjust per-tier.
    "pipeline.embedding_block_size": (32.0, 1024.0),
}

# Keys explicitly excluded from auto-tuning. The autotuner must not move
# these even though they live in the Recommended preset — the comment
# explains why.
_AUTOTUNER_EXCLUDED: dict[str, str] = {
    # Embedding-age half-life is data-driven (depends on actual embedding
    # refresh cadence); a monthly nudge of ±5% would damage the freshness
    # signal in unpredictable ways.
    "pipeline.embedding_age_half_life_days": (
        "data-driven decay constant — depends on actual ingest cadence"
    ),
}


def get_tunable_meta_keys() -> list[str]:
    """Return the keys this tuner is allowed to adjust."""
    return sorted(_META_PARAM_BOUNDS.keys())


def get_excluded_meta_keys() -> dict[str, str]:
    """Return the keys this tuner deliberately does NOT adjust + reasons."""
    return dict(_AUTOTUNER_EXCLUDED)


def _propose_one_key(
    key: str,
    lo: float,
    hi: float,
    current_values: Mapping[str, str | float],
    rng: np.random.Generator,
) -> float | None:
    """Build one candidate value for *key*, or return ``None`` to skip.

    Returns ``None`` when:
    - the key is in ``_AUTOTUNER_EXCLUDED``
    - no current value is available
    - the current value can't be parsed as a number
    """
    if key in _AUTOTUNER_EXCLUDED:
        return None
    raw = current_values.get(key)
    if raw is None:
        return None
    try:
        current = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "meta_tuner: cannot parse current value for %s = %r — skipping",
            key,
            raw,
        )
        return None
    drift = float(rng.uniform(-_META_DRIFT_PCT, _META_DRIFT_PCT))
    candidate = float(np.clip(current * (1.0 + drift), lo, hi))
    # DEFAULT-ON-RULE invariant: never zero a parameter.
    if candidate <= 0.0:  # pragma: no cover — bounds are >0, defensive
        candidate = lo
    return candidate


def propose_meta_parameter_drift(
    current_values: Mapping[str, str | float] | None = None,
    *,
    rng: np.random.Generator | None = None,
) -> dict[str, float]:
    """Return a candidate dict of nudged meta-parameters.

    Strategy: for each tunable key, propose ``current * (1 + drift)``
    where drift ~ Uniform(−5%, +5%). Clamp to per-key bounds. Floor
    all values away from zero per DEFAULT-ON-RULE.md.

    The per-key proposal logic lives in :func:`_propose_one_key`; this
    function just walks ``_META_PARAM_BOUNDS`` and collects results.
    """
    if current_values is None:
        current_values = get_current_weights()
    if rng is None:
        rng = np.random.default_rng()

    proposed: dict[str, float] = {}
    for key, (lo, hi) in _META_PARAM_BOUNDS.items():
        candidate = _propose_one_key(key, lo, hi, current_values, rng)
        if candidate is not None:
            proposed[key] = candidate
    return proposed


class MetaAlgorithmTuner:
    """Lightweight tuner that builds a candidate meta-parameter set.

    V1 strategy is deliberately conservative — propose a small drift,
    let the existing SPRT challenger evaluator + GSC rollback watchdog
    decide whether to keep it. Future versions can add Bayesian
    optimisation on the per-key (lo, hi) box.

    The tuner does NOT write AppSetting directly — it produces a
    candidate dict that the caller (the Celery task) wraps in a
    ``RankingChallenger`` row with ``kind="meta_algorithm"``.
    """

    def propose(self) -> dict[str, float]:
        """Build one candidate meta-parameter dict."""
        return propose_meta_parameter_drift()

    def explain_excluded(self) -> dict[str, str]:
        """Return the keys this tuner deliberately doesn't touch + reasons."""
        return get_excluded_meta_keys()
