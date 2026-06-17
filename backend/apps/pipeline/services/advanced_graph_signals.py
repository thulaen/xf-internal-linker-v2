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
import math
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
    node_blocks: np.ndarray | None = None
    block_transition_matrix: dict[tuple[int, int], float] = field(default_factory=dict)
    lda_topic_vectors: dict[int, tuple[tuple[int, float], ...]] = field(
        default_factory=dict
    )


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
    semantic_scores: list[float] | None = None,
    persona_scores: list[float] | None = None,
) -> list[AdvancedGraphSignalsEvaluation]:
    """Evaluate the 6 advanced graph signals for a batch of host -> dest pairs."""
    n = len(host_dest_pairs)
    if not settings.any_enabled or n == 0:
        return [_inactive_eval("disabled") for _ in range(n)]
    if caches is None:
        return [_inactive_eval("cold_start_no_graph") for _ in range(n)]

    inputs, resolved = _resolve_signal_inputs(
        host_dest_pairs,
        caches,
        is_cross_silo,
        semantic_scores,
        persona_scores,
    )

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
    semantic_scores: list[float] | None = None,
    persona_scores: list[float] | None = None,
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
    host_blocks = np.full(n, -1, dtype=np.int32)
    dest_blocks = np.full(n, -1, dtype=np.int32)
    sbma_resolved = np.zeros(n, dtype=np.uint8)
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
        block[i] = _resolve_sbma_probability(caches, h, d)
        if caches.node_blocks is not None:
            if h < len(caches.node_blocks):
                host_blocks[i] = int(caches.node_blocks[h])
            if d < len(caches.node_blocks):
                dest_blocks[i] = int(caches.node_blocks[d])
            if host_blocks[i] >= 0 and dest_blocks[i] >= 0:
                sbma_resolved[i] = 1
        elif (h, d) in caches.block_probabilities:
            sbma_resolved[i] = 1
        flat[i] = _resolve_flat_distance(caches, h, d, semantic_scores, i)
        persona[i] = _resolve_persona_match(caches, h, d, persona_scores, i)

    inputs = {
        "spectral_scores": spectral,
        "transition_counts": transition,
        "out_degrees": out_deg,
        "local_degrees": local,
        "global_degrees": glob,
        "block_probabilities": block,
        "host_blocks": host_blocks,
        "dest_blocks": dest_blocks,
        "sbma_resolved": sbma_resolved,
        "flat_distances": flat,
        "density_gradients": density,
        "persona_matches": persona,
        "is_cross_silo": np.asarray(is_cross_silo, dtype=np.uint8),
    }
    return inputs, resolved


def csbr_persona_match_from_metadata(
    host_metadata: dict[str, Any] | None,
    destination_metadata: dict[str, Any] | None,
) -> float:
    """Return CSBR topic similarity from stored page metadata."""
    host_topics = csbr_topic_vector_from_metadata(host_metadata)
    destination_topics = csbr_topic_vector_from_metadata(destination_metadata)
    return _jensen_shannon_topic_similarity(host_topics, destination_topics)


def csbr_topic_vector_from_metadata(
    metadata: dict[str, Any] | None,
) -> tuple[tuple[int, float], ...]:
    """Return stored CSBR topic weights from page metadata."""
    return _topic_pairs_from_metadata(metadata)


def _topic_pairs_from_metadata(
    metadata: dict[str, Any] | None,
) -> tuple[tuple[int, float], ...]:
    if not metadata:
        return ()
    for key in ("lda_topics", "lda_topic_vector", "lda_topic_vectors"):
        pairs = _normalise_topic_pairs(metadata.get(key))
        if pairs:
            return pairs
    return ()


def _normalise_topic_pairs(raw: Any) -> tuple[tuple[int, float], ...]:
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, (list, tuple)):
        items = raw
    else:
        return ()
    pairs: list[tuple[int, float]] = []
    for item in items:
        if isinstance(item, dict):
            topic_id = item.get("topic_id", item.get("topic"))
            weight = item.get("weight", item.get("probability"))
        else:
            try:
                topic_id, weight = item
            except (TypeError, ValueError):
                continue
        try:
            topic_int = int(topic_id)
            weight_float = float(weight)
        except (TypeError, ValueError):
            continue
        if weight_float > 0.0:
            pairs.append((topic_int, weight_float))
    return tuple(pairs)


def _resolve_persona_match(
    caches: AdvancedGraphSignalsCaches,
    host_index: int,
    dest_index: int,
    persona_scores: list[float] | None,
    position: int,
) -> float:
    cached = caches.persona_matches.get((host_index, dest_index))
    if cached is not None:
        return _clamp_unit_interval(float(cached))
    if persona_scores is not None and position < len(persona_scores):
        return _clamp_unit_interval(float(persona_scores[position]))
    return _jensen_shannon_topic_similarity(
        caches.lda_topic_vectors.get(host_index, ()),
        caches.lda_topic_vectors.get(dest_index, ()),
    )


def _jensen_shannon_topic_similarity(
    host_topics: tuple[tuple[int, float], ...],
    destination_topics: tuple[tuple[int, float], ...],
) -> float:
    host_dist = _normalised_distribution(host_topics)
    dest_dist = _normalised_distribution(destination_topics)
    if not host_dist or not dest_dist:
        return 0.0
    topic_ids = host_dist.keys() | dest_dist.keys()
    midpoint = {
        topic_id: 0.5 * (host_dist.get(topic_id, 0.0) + dest_dist.get(topic_id, 0.0))
        for topic_id in topic_ids
    }
    divergence = 0.5 * _kl_divergence(host_dist, midpoint, topic_ids)
    divergence += 0.5 * _kl_divergence(dest_dist, midpoint, topic_ids)
    return _clamp_unit_interval(1.0 - divergence)


def _normalised_distribution(
    pairs: tuple[tuple[int, float], ...],
) -> dict[int, float]:
    totals: dict[int, float] = {}
    for topic_id, weight in pairs:
        if weight > 0.0:
            totals[topic_id] = totals.get(topic_id, 0.0) + weight
    total_weight = sum(totals.values())
    if total_weight <= 0.0:
        return {}
    return {
        topic_id: weight / total_weight
        for topic_id, weight in totals.items()
    }


def _kl_divergence(
    dist: dict[int, float],
    reference: dict[int, float],
    topic_ids: set[int],
) -> float:
    total = 0.0
    for topic_id in topic_ids:
        probability = dist.get(topic_id, 0.0)
        if probability > 0.0:
            total += probability * math.log2(probability / reference[topic_id])
    return total


def _clamp_unit_interval(value: float) -> float:
    return min(1.0, max(0.0, value))


def _resolve_flat_distance(
    caches: AdvancedGraphSignalsCaches,
    host_index: int,
    dest_index: int,
    semantic_scores: list[float] | None,
    position: int,
) -> float:
    """Resolve RGSD flat distance from cache or the current semantic score."""
    cached = caches.flat_distances.get((host_index, dest_index))
    if cached is not None:
        return cached
    if semantic_scores is None or position >= len(semantic_scores):
        return 1.0
    return 1.0 - min(1.0, max(0.0, float(semantic_scores[position])))


def _resolve_sbma_probability(
    caches: AdvancedGraphSignalsCaches,
    host_index: int,
    dest_index: int,
) -> float:
    """Resolve one SBMA block probability from compact block cache data."""
    if caches.node_blocks is None:
        return caches.block_probabilities.get((host_index, dest_index), 0.0)
    if host_index >= len(caches.node_blocks) or dest_index >= len(caches.node_blocks):
        return 0.0
    host_block = int(caches.node_blocks[host_index])
    dest_block = int(caches.node_blocks[dest_index])
    if host_block < 0 or dest_block < 0:
        return 0.0
    return caches.block_transition_matrix.get((host_block, dest_block), 0.0)


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
            "fallback_triggered": fallback or not bool(inputs["sbma_resolved"][i]),
            "score": scores["score_sbma"],
            "block_probability": float(inputs["block_probabilities"][i]),
            "host_block": int(inputs["host_blocks"][i]),
            "dest_block": int(inputs["dest_blocks"][i]),
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
