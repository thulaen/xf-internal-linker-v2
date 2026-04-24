"""FR-099 through FR-105 dispatcher — evaluates all 7 graph-topology signals
for a single (host, dest) pair and returns the combined weighted contribution
plus per-signal diagnostics.

This module is called from ranker.py's score_destination_matches AFTER the
existing 15-element composite score is computed. The 7 signals' weighted
contributions are added to score_final; their per-signal raw scores and
diagnostics are attached to the Suggestion row.

Design rationale: rather than extending the 15-element numpy array to 22
(invasive change to scoring loop), we treat FR-099-FR-105 as an
independent additive layer. This keeps the existing hot-path scoring code
untouched and allows the 7 signals to be cleanly on/off per-setting.

Each signal has its own Settings dataclass and Evaluation dataclass.
Signals with disabled=true return score_component=0.0 and
fallback_triggered=True. Cold-start (no cache yet) also returns 0.0.

Full specs: docs/specs/fr099-*.md through docs/specs/fr105-*.md
Gates: docs/RANKING-GATES.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TypeAlias

from .articulation_point_boost import (
    ArticulationPointCache,
    TAPBEvaluation,
    TAPBSettings,
    evaluate_tapb,
)
from .bridge_edge_redundancy import (
    BERPEvaluation,
    BERPSettings,
    BridgeEdgeCache,
    evaluate_berp,
)
from .dangling_authority_redistribution import (
    DARBEvaluation,
    DARBSettings,
    evaluate_darb,
)
from .host_topic_entropy import (
    HGTEEvaluation,
    HGTESettings,
    HostSiloDistributionCache,
    evaluate_hgte,
)
from .katz_marginal_info import (
    KatzCache,
    KMIGEvaluation,
    KMIGSettings,
    evaluate_kmig,
)
from .kcore_integration import (
    KCIBEvaluation,
    KCIBSettings,
    KCoreCache,
    evaluate_kcib,
)
from .search_query_alignment import (
    QueryTFIDFCache,
    RSQVAEvaluation,
    RSQVASettings,
    evaluate_rsqva,
)

ContentKey: TypeAlias = tuple[int, str]


@dataclass(frozen=True, slots=True)
class FR099FR105Settings:
    """Combined settings for all 7 signals. Loaded once per pipeline run."""

    darb: DARBSettings = field(default_factory=DARBSettings)
    kmig: KMIGSettings = field(default_factory=KMIGSettings)
    tapb: TAPBSettings = field(default_factory=TAPBSettings)
    kcib: KCIBSettings = field(default_factory=KCIBSettings)
    berp: BERPSettings = field(default_factory=BERPSettings)
    hgte: HGTESettings = field(default_factory=HGTESettings)
    rsqva: RSQVASettings = field(default_factory=RSQVASettings)

    @property
    def any_enabled(self) -> bool:
        """Fast-path check — skip cache building if all 7 are disabled."""
        return (
            self.darb.enabled
            or self.kmig.enabled
            or self.tapb.enabled
            or self.kcib.enabled
            or self.berp.enabled
            or self.hgte.enabled
            or self.rsqva.enabled
        )


@dataclass(frozen=True, slots=True)
class FR099FR105Caches:
    """Combined precomputed caches. Nullable individually — signals with
    missing caches return neutral fallback."""

    katz_cache: KatzCache | None = None
    articulation_cache: ArticulationPointCache | None = None
    kcore_cache: KCoreCache | None = None
    bridge_cache: BridgeEdgeCache | None = None
    silo_cache: HostSiloDistributionCache | None = None
    query_cache: QueryTFIDFCache | None = None
    # Reused from existing pipeline_data — no duplicate cache.
    # existing_outgoing_counts is passed directly into evaluate_darb.


@dataclass(frozen=True, slots=True)
class FR099FR105Evaluation:
    """Combined result of evaluating all 7 signals for one candidate pair.

    Attributes:
        weighted_contribution: the scalar added to score_final.
            Sum of (score_i × ranking_weight_i) for i in {darb, kmig, tapb, kcib, hgte, rsqva}
            PLUS berp_contribution (which is already signed negative).
        per_signal_scores: dict with 7 raw score_<signal> floats for the
            Suggestion.score_<signal> columns.
        per_signal_diagnostics: dict with 7 <signal>_diagnostics sub-dicts
            for the Suggestion.<signal>_diagnostics JSONFields.
    """

    weighted_contribution: float
    per_signal_scores: dict[str, float]
    per_signal_diagnostics: dict[str, dict[str, Any]]


def evaluate_all_fr099_fr105(
    *,
    host_key: ContentKey,
    destination_key: ContentKey,
    host_content_value: float | None,
    dest_silo_id: int | None,
    existing_outgoing_counts: Mapping[ContentKey, int] | None,
    caches: FR099FR105Caches,
    settings: FR099FR105Settings,
) -> FR099FR105Evaluation:
    """Evaluate all 7 signals for one (host, dest) pair and combine them.

    Returns a FR099FR105Evaluation with:
      - weighted_contribution: added to score_final by the caller
      - per_signal_scores: 7 raw scores for Suggestion.score_<signal> columns
      - per_signal_diagnostics: 7 diagnostics blobs for Suggestion.<signal>_diagnostics

    Thread-safe: all inputs are immutable or read-only.
    """
    # --- FR-099 DARB ---
    darb_eval = evaluate_darb(
        host_key=host_key,
        host_content_value=host_content_value,
        existing_outgoing_counts=existing_outgoing_counts,
        settings=settings.darb,
    )

    # --- FR-100 KMIG ---
    kmig_eval = evaluate_kmig(
        host_key=host_key,
        destination_key=destination_key,
        katz_cache=caches.katz_cache,
        settings=settings.kmig,
    )

    # --- FR-101 TAPB ---
    tapb_eval = evaluate_tapb(
        host_key=host_key,
        articulation_cache=caches.articulation_cache,
        settings=settings.tapb,
    )

    # --- FR-102 KCIB ---
    kcib_eval = evaluate_kcib(
        host_key=host_key,
        destination_key=destination_key,
        kcore_cache=caches.kcore_cache,
        settings=settings.kcib,
    )

    # --- FR-103 BERP ---
    berp_eval = evaluate_berp(
        host_key=host_key,
        destination_key=destination_key,
        bridge_cache=caches.bridge_cache,
        settings=settings.berp,
    )

    # --- FR-104 HGTE ---
    hgte_eval = evaluate_hgte(
        host_key=host_key,
        dest_silo_id=dest_silo_id,
        silo_cache=caches.silo_cache,
        settings=settings.hgte,
    )

    # --- FR-105 RSQVA ---
    rsqva_eval = evaluate_rsqva(
        host_key=host_key,
        destination_key=destination_key,
        query_cache=caches.query_cache,
        settings=settings.rsqva,
    )

    # Weighted combine. BERP's score_component is already signed negative.
    weighted_contribution = (
        darb_eval.score_component * settings.darb.ranking_weight
        + kmig_eval.score_component * settings.kmig.ranking_weight
        + tapb_eval.score_component * settings.tapb.ranking_weight
        + kcib_eval.score_component * settings.kcib.ranking_weight
        + berp_eval.score_component * settings.berp.ranking_weight
        + hgte_eval.score_component * settings.hgte.ranking_weight
        + rsqva_eval.score_component * settings.rsqva.ranking_weight
    )

    return FR099FR105Evaluation(
        weighted_contribution=float(weighted_contribution),
        per_signal_scores={
            "score_darb": float(darb_eval.score_component),
            "score_kmig": float(kmig_eval.score_component),
            "score_tapb": float(tapb_eval.score_component),
            "score_kcib": float(kcib_eval.score_component),
            "score_berp": float(berp_eval.score_component),
            "score_hgte": float(hgte_eval.score_component),
            "score_rsqva": float(rsqva_eval.score_component),
        },
        per_signal_diagnostics={
            "darb_diagnostics": dict(darb_eval.diagnostics),
            "kmig_diagnostics": dict(kmig_eval.diagnostics),
            "tapb_diagnostics": dict(tapb_eval.diagnostics),
            "kcib_diagnostics": dict(kcib_eval.diagnostics),
            "berp_diagnostics": dict(berp_eval.diagnostics),
            "hgte_diagnostics": dict(hgte_eval.diagnostics),
            "rsqva_diagnostics": dict(rsqva_eval.diagnostics),
        },
    )
