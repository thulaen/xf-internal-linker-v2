"""Forward-declared Phase 2 ranking signal weights — Blocks A through F.

Covers FR-099 through FR-151 (53 feature requests, 106 keys total):
  - Block A: Classical IR scoring models (FR-099 .. FR-107)
  - Block B: Proximity and dependence models (FR-108 .. FR-115)
  - Block C: Graph authority and centrality (FR-116 .. FR-125)
  - Block D: Result diversification (FR-126 .. FR-133)
  - Block E: Time-series / trend / change detection (FR-134 .. FR-143)
  - Block F: Streaming sketches and approximate counting (FR-144 .. FR-151)

These keys are inert until their corresponding FR is implemented and reads them.
They live in a separate file to keep each module under the file-length limit.

``FORWARD_DECLARED_WEIGHTS_PHASE2_SIGNALS_A_F`` is merged into
``RECOMMENDED_PRESET_WEIGHTS`` at import time by the main module.

All keys use ``.enabled="true"`` and ``.ranking_weight="0.0"`` (inert by default).

Source specs: docs/specs/fr099-*.md through docs/specs/fr151-*.md
"""

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_SIGNALS_A_F: dict[str, str] = {
    # =====================================================================
    # Block A — Classical IR scoring models (FR-099 .. FR-107)
    # =====================================================================
    # FR-099 — BM25+ Lower-Bound Term-Frequency Normalization
    "bm25_plus.enabled": "true",
    "bm25_plus.ranking_weight": "0.0",
    # FR-100 — BM25L Length-Unbiased Term Weighting
    "bm25l.enabled": "true",
    "bm25l.ranking_weight": "0.0",
    # FR-101 — DFR PL2 (Divergence From Randomness, Poisson + Laplace)
    "dfr_pl2.enabled": "true",
    "dfr_pl2.ranking_weight": "0.0",
    # FR-102 — DFR InL2 (Inverse Document Frequency + Laplace Aftereffect)
    "dfr_inl2.enabled": "true",
    "dfr_inl2.ranking_weight": "0.0",
    # FR-103 — DFR DPH (Parameter-Free Divergence From Randomness)
    "dfr_dph.enabled": "true",
    "dfr_dph.ranking_weight": "0.0",
    # FR-104 — Axiomatic F2-EXP Retrieval Function
    "axiomatic_f2exp.enabled": "true",
    "axiomatic_f2exp.ranking_weight": "0.0",
    # FR-105 — Two-Stage Language Model (Zhai & Lafferty)
    "two_stage_lm.enabled": "true",
    "two_stage_lm.ranking_weight": "0.0",
    # FR-106 — Positional Language Model
    "positional_lm.enabled": "true",
    "positional_lm.ranking_weight": "0.0",
    # FR-107 — Relevance Model RM3 (Pseudo-Relevance Feedback)
    "rm3.enabled": "true",
    "rm3.ranking_weight": "0.0",
    # =====================================================================
    # Block B — Proximity and dependence models (FR-108 .. FR-115)
    # =====================================================================
    # FR-108 — Sequential Dependence Model (SDM, Metzler & Croft)
    "sdm.enabled": "true",
    "sdm.ranking_weight": "0.0",
    # FR-109 — Weighted Sequential Dependence Model (WSDM)
    "wsdm_weighted.enabled": "true",
    "wsdm_weighted.ranking_weight": "0.0",
    # FR-110 — Full Dependence Model (FDM)
    "fdm.enabled": "true",
    "fdm.ranking_weight": "0.0",
    # FR-111 — BM25TP Term-Proximity Extension
    "bm25tp.enabled": "true",
    "bm25tp.ranking_weight": "0.0",
    # FR-112 — Minimum-Span Proximity Score
    "minspan_prox.enabled": "true",
    "minspan_prox.ranking_weight": "0.0",
    # FR-113 — Ordered-Span Proximity Score
    "ordered_span_prox.enabled": "true",
    "ordered_span_prox.ranking_weight": "0.0",
    # FR-114 — BoolProx Boolean-with-Proximity Ranking
    "boolprox.enabled": "true",
    "boolprox.ranking_weight": "0.0",
    # FR-115 — Markov Random Field Per-Field Retrieval
    "mrf_per_field.enabled": "true",
    "mrf_per_field.ranking_weight": "0.0",
    # =====================================================================
    # Block C — Graph authority and centrality (FR-116 .. FR-125)
    # =====================================================================
    # FR-116 — HITS Authority Score
    "hits_authority.enabled": "true",
    "hits_authority.ranking_weight": "0.0",
    # FR-117 — HITS Hub Score
    "hits_hub.enabled": "true",
    "hits_hub.ranking_weight": "0.0",
    # FR-118 — TrustRank Propagation
    "trustrank.enabled": "true",
    "trustrank.ranking_weight": "0.0",
    # FR-119 — Anti-TrustRank (inverse propagation)
    "anti_trustrank.enabled": "true",
    "anti_trustrank.ranking_weight": "0.0",
    # FR-120 — SALSA Stochastic Approach to Link-Structure Analysis
    "salsa.enabled": "true",
    "salsa.ranking_weight": "0.0",
    # FR-121 — SimRank Structural Similarity
    "simrank.enabled": "true",
    "simrank.ranking_weight": "0.0",
    # FR-122 — Katz Centrality
    "katz.enabled": "true",
    "katz.ranking_weight": "0.0",
    # FR-123 — K-Shell Coreness
    "kshell.enabled": "true",
    "kshell.ranking_weight": "0.0",
    # FR-124 — Harmonic Centrality
    "harmonic.enabled": "true",
    "harmonic.ranking_weight": "0.0",
    # FR-125 — LeaderRank
    "leaderrank.enabled": "true",
    "leaderrank.ranking_weight": "0.0",
    # =====================================================================
    # Block D — Result diversification (FR-126 .. FR-133)
    # =====================================================================
    # FR-126 — IA-Select Intent-Aware Diversification
    "ia_select.enabled": "true",
    "ia_select.ranking_weight": "0.0",
    # FR-127 — xQuAD Aspect Diversification
    "xquad.enabled": "true",
    "xquad.ranking_weight": "0.0",
    # FR-128 — PM-2 Proportional Diversification
    "pm2.enabled": "true",
    "pm2.ranking_weight": "0.0",
    # FR-129 — Determinantal Point Process Reranking
    "dpp.enabled": "true",
    "dpp.ranking_weight": "0.0",
    # FR-130 — Submodular Coverage Reranking
    "submod_cov.enabled": "true",
    "submod_cov.ranking_weight": "0.0",
    # FR-131 — Portfolio Theory Reranking
    "portfolio.enabled": "true",
    "portfolio.ranking_weight": "0.0",
    # FR-132 — Latent Diversity Model
    "ldm.enabled": "true",
    "ldm.ranking_weight": "0.0",
    # FR-133 — Quota-Based Diversity
    "quota_div.enabled": "true",
    "quota_div.ranking_weight": "0.0",
    # =====================================================================
    # Block E — Time-series / trend / change detection (FR-134 .. FR-143)
    # =====================================================================
    # FR-134 — Kleinberg Burst Detection
    "kleinberg_burst.enabled": "true",
    "kleinberg_burst.ranking_weight": "0.0",
    # FR-135 — PELT Change-Point Detection
    "pelt_changepoint.enabled": "true",
    "pelt_changepoint.ranking_weight": "0.0",
    # FR-136 — CUSUM Cumulative Anomaly
    "cusum.enabled": "true",
    "cusum.ranking_weight": "0.0",
    # FR-137 — STL Seasonal-Trend Decomposition
    "stl_decomposition.enabled": "true",
    "stl_decomposition.ranking_weight": "0.0",
    # FR-138 — Mann-Kendall Nonparametric Trend Test
    "mann_kendall.enabled": "true",
    "mann_kendall.ranking_weight": "0.0",
    # FR-139 — Theil-Sen Robust Slope Estimator
    "theil_sen.enabled": "true",
    "theil_sen.ranking_weight": "0.0",
    # FR-140 — Fourier Periodicity Strength
    "fourier_periodicity.enabled": "true",
    "fourier_periodicity.ranking_weight": "0.0",
    # FR-141 — Autocorrelation Lag-k Signal
    "autocorrelation.enabled": "true",
    "autocorrelation.ranking_weight": "0.0",
    # FR-142 — Partial Autocorrelation Signal
    "partial_autocorrelation.enabled": "true",
    "partial_autocorrelation.ranking_weight": "0.0",
    # FR-143 — EWMA Smoothed Click Rate
    "ewma_click.enabled": "true",
    "ewma_click.ranking_weight": "0.0",
    # =====================================================================
    # Block F — Streaming sketches and approximate counting (FR-144 .. FR-151)
    # =====================================================================
    # FR-144 — HyperLogLog Unique Visitors
    "hyperloglog.enabled": "true",
    "hyperloglog.ranking_weight": "0.0",
    # FR-145 — HyperLogLog++ Visitor Estimator
    "hyperloglog_plus.enabled": "true",
    "hyperloglog_plus.ranking_weight": "0.0",
    # FR-146 — Count-Min Sketch Anchor Rarity
    "countmin_sketch.enabled": "true",
    "countmin_sketch.ranking_weight": "0.0",
    # FR-147 — Count Sketch Signed Frequency
    "count_sketch.enabled": "true",
    "count_sketch.ranking_weight": "0.0",
    # FR-148 — Space-Saving Top-K Anchors
    "space_saving.enabled": "true",
    "space_saving.ranking_weight": "0.0",
    # FR-149 — t-Digest Quantile Tracker
    "t_digest.enabled": "true",
    "t_digest.ranking_weight": "0.0",
    # FR-150 — Lossy Counting Frequency
    "lossy_counting.enabled": "true",
    "lossy_counting.ranking_weight": "0.0",
    # FR-151 — b-Bit MinHash Similarity
    "b_bit_minhash.enabled": "true",
    "b_bit_minhash.ranking_weight": "0.0",
}
