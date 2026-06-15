"""Advanced Graph Signals (FR-260 to FR-265) dispatcher.

Evaluates the 6 advanced graph signals for a batch of candidates using the
Rust hot-path kernel (RUST-FIRST.md).

Signals:
- FR-260: Time-as-Operator Spectral Decay (TOSD)
- FR-261: Directed Sequential Transition Probability (DSTP)
- FR-262: In-Community Popularity Contrast (ICPC)
- FR-263: Stochastic Block Model Affinity (SBMA)
- FR-264: Riemannian Geodesic Semantic Distance (RGSD)
- FR-265: Cross-Silo Bridging Reward (CSBR)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, TypeAlias

import numpy as np

from apps.pipeline.services.rust_kernels import load_kernel

logger = logging.getLogger(__name__)

ContentKey: TypeAlias = tuple[int, str]

_SIGNAL_KEYS = ("tosd", "dstp", "icpc", "sbma", "rgsd", "csbr")


@dataclass(frozen=True, slots=True)
class TOSDSettings:
    enabled: bool = True
    ranking_weight: float = 0.06
    filter_strength: float = 0.8


@dataclass(frozen=True, slots=True)
class DSTPSettings:
    enabled: bool = True
    ranking_weight: float = 0.08
    smoothing_alpha: float = 5.0


@dataclass(frozen=True, slots=True)
class ICPCSettings:
    enabled: bool = True
    ranking_weight: float = 0.04
    min_community_size: int = 10


@dataclass(frozen=True, slots=True)
class SBMASettings:
    enabled: bool = True
    ranking_weight: float = 0.05
    num_blocks: int = 20


@dataclass(frozen=True, slots=True)
class RGSDSettings:
    enabled: bool = True
    ranking_weight: float = 0.10
    curvature_penalty: float = 1.5


@dataclass(frozen=True, slots=True)
class CSBRSettings:
    enabled: bool = True
    ranking_weight: float = 0.05
    min_overlap_threshold: float = 0.7


@dataclass(frozen=True, slots=True)
class AdvancedGraphSignalsSettings:
    """Combined settings for FR-260 to FR-265."""
    tosd: TOSDSettings = field(default_factory=TOSDSettings)
    dstp: DSTPSettings = field(default_factory=DSTPSettings)
    icpc: ICPCSettings = field(default_factory=ICPCSettings)
    sbma: SBMASettings = field(default_factory=SBMASettings)
    rgsd: RGSDSettings = field(default_factory=RGSDSettings)
    csbr: CSBRSettings = field(default_factory=CSBRSettings)

    @property
    def any_enabled(self) -> bool:
        return (
            self.tosd.enabled
            or self.dstp.enabled
            or self.icpc.enabled
            or self.sbma.enabled
            or self.rgsd.enabled
            or self.csbr.enabled
        )


@dataclass(frozen=True, slots=True)
class AdvancedGraphSignalsCaches:
    """Precomputed data for advanced graph signals.

    Per-node arrays are indexed by ``node_to_index``. TOSD/ICPC/RGSD read the
    DESTINATION node's value (they describe the destination's structural role);
    DSTP reads the HOST's out-transition total. Pair maps are keyed
    ``(host_index, dest_index)``.
    """
    node_to_index: dict[ContentKey, int]
    spectral_scores: np.ndarray
    transition_counts: dict[tuple[int, int], int]
    out_degrees: np.ndarray
    local_degrees: np.ndarray
    global_degrees: np.ndarray
    block_probabilities: dict[tuple[int, int], float]
    flat_distances: dict[tuple[int, int], float]
    density_gradients: np.ndarray
    persona_matches: dict[tuple[int, int], float]


@dataclass(frozen=True, slots=True)
class AdvancedGraphSignalsEvaluation:
    """Evaluation result for a single candidate."""
    weighted_contribution: float
    per_signal_scores: dict[str, float]
    per_signal_diagnostics: dict[str, dict[str, Any]]


def evaluate_advanced_graph_signals_batch(
    host_dest_pairs: list[tuple[ContentKey, ContentKey]],
    caches: AdvancedGraphSignalsCaches | None,
    settings: AdvancedGraphSignalsSettings,
    is_cross_silo: list[bool],
) -> list[AdvancedGraphSignalsEvaluation]:
    """Evaluate the 6 advanced graph signals for a batch of host -> dest pairs."""
    n = len(host_dest_pairs)
    if not settings.any_enabled or n == 0:
        return [_inactive_eval("disabled") for _ in range(n)]
    if caches is None:
        return [_inactive_eval("cold_start_no_graph") for _ in range(n)]

    inputs, resolved = _resolve_signal_inputs(host_dest_pairs, caches, is_cross_silo)

    try:
        kernel = load_kernel("extensions.advanced_graph_signals", "evaluate_batch")
        outputs = kernel.evaluate_batch(
            inputs["spectral_scores"],
            settings.tosd.filter_strength,
            inputs["transition_counts"],
            inputs["out_degrees"],
            settings.dstp.smoothing_alpha,
            inputs["local_degrees"],
            inputs["global_degrees"],
            inputs["block_probabilities"],
            inputs["flat_distances"],
            inputs["density_gradients"],
            settings.rgsd.curvature_penalty,
            inputs["is_cross_silo"],
            inputs["persona_matches"],
            settings.csbr.min_overlap_threshold,
        )
    except Exception:
        logger.exception("Advanced graph signals kernel failed")
        return [_inactive_eval("kernel_error") for _ in range(n)]

    return [
        _build_evaluation(i, inputs, settings, outputs, resolved[i]) for i in range(n)
    ]


def _resolve_signal_inputs(
    host_dest_pairs: list[tuple[ContentKey, ContentKey]],
    caches: AdvancedGraphSignalsCaches,
    is_cross_silo: list[bool],
) -> tuple[dict[str, np.ndarray], list[bool]]:
    """Gather per-candidate kernel inputs from the caches.

    ``resolved[i]`` is False when either endpoint is missing from the graph; the
    caller forces such candidates to the neutral 0.0 fallback.
    """
    n = len(host_dest_pairs)
    spectral = np.zeros(n, dtype=np.float64)
    transition = np.zeros(n, dtype=np.int32)
    out_deg = np.zeros(n, dtype=np.int32)
    local = np.zeros(n, dtype=np.int32)
    glob = np.zeros(n, dtype=np.int32)
    block = np.zeros(n, dtype=np.float64)
    flat = np.ones(n, dtype=np.float64)  # missing pair = farthest -> neutral RGSD
    density = np.zeros(n, dtype=np.float64)
    persona = np.zeros(n, dtype=np.float64)
    resolved = [False] * n

    for i, (host, dest) in enumerate(host_dest_pairs):
        h = caches.node_to_index.get(host, -1)
        d = caches.node_to_index.get(dest, -1)
        if h < 0 or d < 0:
            continue
        resolved[i] = True
        # Destination-centric per-node signals (TOSD / ICPC / RGSD).
        if d < len(caches.spectral_scores):
            spectral[i] = caches.spectral_scores[d]
        if d < len(caches.local_degrees):
            local[i] = caches.local_degrees[d]
        if d < len(caches.global_degrees):
            glob[i] = caches.global_degrees[d]
        if d < len(caches.density_gradients):
            density[i] = caches.density_gradients[d]
        # Host-centric: DSTP's count(A -> *) total out-transitions.
        if h < len(caches.out_degrees):
            out_deg[i] = caches.out_degrees[h]
        # Pair lookups keyed (host_index, dest_index).
        transition[i] = caches.transition_counts.get((h, d), 0)
        block[i] = caches.block_probabilities.get((h, d), 0.0)
        flat[i] = caches.flat_distances.get((h, d), 1.0)
        persona[i] = caches.persona_matches.get((h, d), 0.0)

    inputs = {
        "spectral_scores": spectral,
        "transition_counts": transition,
        "out_degrees": out_deg,
        "local_degrees": local,
        "global_degrees": glob,
        "block_probabilities": block,
        "flat_distances": flat,
        "density_gradients": density,
        "persona_matches": persona,
        "is_cross_silo": np.asarray(is_cross_silo, dtype=np.uint8),
    }
    return inputs, resolved


def _build_evaluation(
    i: int,
    inputs: dict[str, np.ndarray],
    settings: AdvancedGraphSignalsSettings,
    outputs: dict[str, Any],
    resolved_i: bool,
) -> AdvancedGraphSignalsEvaluation:
    """Assemble one candidate's scores, weighted contribution, and diagnostics."""
    fallback = not resolved_i

    def score_of(key: str, enabled: bool) -> float:
        # A missing host/dest -> neutral 0.0 for every signal, overriding any value
        # the kernel produced from default inputs (e.g. TOSD lambda=0 -> 1.0).
        if not enabled or fallback:
            return 0.0
        return float(outputs[key][i])

    scores = {
        "score_tosd": score_of("score_tosd", settings.tosd.enabled),
        "score_dstp": score_of("score_dstp", settings.dstp.enabled),
        "score_icpc": score_of("score_icpc", settings.icpc.enabled),
        "score_sbma": score_of("score_sbma", settings.sbma.enabled),
        "score_rgsd": score_of("score_rgsd", settings.rgsd.enabled),
        "score_csbr": score_of("score_csbr", settings.csbr.enabled),
    }
    contrib = (
        scores["score_tosd"] * settings.tosd.ranking_weight
        + scores["score_dstp"] * settings.dstp.ranking_weight
        + scores["score_icpc"] * settings.icpc.ranking_weight
        + scores["score_sbma"] * settings.sbma.ranking_weight
        + scores["score_rgsd"] * settings.rgsd.ranking_weight
        + scores["score_csbr"] * settings.csbr.ranking_weight
    )
    return AdvancedGraphSignalsEvaluation(
        weighted_contribution=contrib,
        per_signal_scores=scores,
        per_signal_diagnostics=_build_diagnostics(i, inputs, settings, scores, fallback),
    )


def _build_diagnostics(
    i: int,
    inputs: dict[str, np.ndarray],
    settings: AdvancedGraphSignalsSettings,
    scores: dict[str, float],
    fallback: bool,
) -> dict[str, dict[str, Any]]:
    """Build the per-signal diagnostics each spec defines (stored as JSON)."""
    return {
        "tosd_diagnostics": {
            "enabled": settings.tosd.enabled,
            "fallback_triggered": fallback,
            "score": scores["score_tosd"],
            "raw_lambda": float(inputs["spectral_scores"][i]),
            "filter_strength": settings.tosd.filter_strength,
        },
        "dstp_diagnostics": {
            "enabled": settings.dstp.enabled,
            "fallback_triggered": fallback,
            "score": scores["score_dstp"],
            "transition_count": int(inputs["transition_counts"][i]),
            "out_degree": int(inputs["out_degrees"][i]),
            "smoothing_alpha": settings.dstp.smoothing_alpha,
        },
        "icpc_diagnostics": {
            "enabled": settings.icpc.enabled,
            "fallback_triggered": fallback,
            "score": scores["score_icpc"],
            "local_indegree": int(inputs["local_degrees"][i]),
            "global_indegree": int(inputs["global_degrees"][i]),
            "min_community_size": settings.icpc.min_community_size,
        },
        "sbma_diagnostics": {
            "enabled": settings.sbma.enabled,
            "fallback_triggered": fallback,
            "score": scores["score_sbma"],
            "block_probability": float(inputs["block_probabilities"][i]),
            "num_blocks": settings.sbma.num_blocks,
        },
        "rgsd_diagnostics": {
            "enabled": settings.rgsd.enabled,
            "fallback_triggered": fallback,
            "score": scores["score_rgsd"],
            "flat_distance": float(inputs["flat_distances"][i]),
            "density_gradient": float(inputs["density_gradients"][i]),
            "curvature_penalty": settings.rgsd.curvature_penalty,
        },
        "csbr_diagnostics": {
            "enabled": settings.csbr.enabled,
            "fallback_triggered": fallback,
            "score": scores["score_csbr"],
            "is_cross_silo": bool(inputs["is_cross_silo"][i]),
            "persona_match": float(inputs["persona_matches"][i]),
            "min_overlap_threshold": settings.csbr.min_overlap_threshold,
        },
    }


def _inactive_eval(reason: str) -> AdvancedGraphSignalsEvaluation:
    """A neutral evaluation for the disabled / cold-start / kernel-error cases."""
    return AdvancedGraphSignalsEvaluation(
        weighted_contribution=0.0,
        per_signal_scores={f"score_{s}": 0.0 for s in _SIGNAL_KEYS},
        per_signal_diagnostics={
            f"{s}_diagnostics": {
                "enabled": False,
                "fallback_triggered": True,
                "reason": reason,
                "score": 0.0,
            }
            for s in _SIGNAL_KEYS
        },
    )
