"""Measure-twice, convinced-once embedding quality gate (plan Part 9, FR-236).

Three gates decide whether a new embedding may replace an existing one:

  Gate 0 — first-time embed: if there is no existing vector, accept.
  Gate 1 — provider-quality ranking: reject if the new provider ranks lower
           than the old one by more than ``gate_quality_delta_threshold``.
           Ranking is populated by the bake-off (plan Part 4).
  Gate 2 — change detection: if ``cos(old, new) > gate_noop_cosine_threshold``,
           the new vector is effectively identical — NOOP (no write, no archive).
  Gate 3 — stability: re-sample the same provider on the same text. If
           ``cos(new, sample2) < gate_stability_threshold``, the result is
           unstable (transient API flake, mixed context); reject.

Research grounding (docstring only — full citations live in FR-236 spec):
  * Reimers & Gurevych 2019 — SBERT chunked pooling.
  * Metropolis & Ulam 1949 — Monte Carlo double-sampling stability.
  * Nygard 2018 — circuit-breaker pattern (quality-gate provider regression).
  * Voorhees 1999 / Järvelin & Kekäläinen 2002 — NDCG as the ranking signal.
  * US Patent 11,256,687 — re-ranking with confidence gating (prior art).

Performance contract (plan budget ≤32 MB RAM, ≤128 MB disk):
  * Per-item peak: 3 × dim × 4 bytes = ~36 KB at dim=3072.
  * Uses only ``np.dot`` and ``np.linalg.norm`` on unit vectors — O(dim) per call.
  * Gate-decision logs: bulk-created 500 at a time, <200 bytes per row.
  * No model loading happens here; Gate 3's re-sample is delegated to the
    current provider (already in process cache).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# Thresholds (overridable via AppSetting — keep defaults conservative).
_DEFAULT_QUALITY_DELTA = -0.05
_DEFAULT_NOOP_COSINE = 0.9999
_DEFAULT_STABILITY = 0.99


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Outcome of ``QualityGate.evaluate``. Hashable for set membership."""

    action: str          # "REPLACE" | "REJECT" | "NOOP" | "ACCEPT_NEW"
    reason: str          # short code
    score_delta: float   # interpretation depends on which gate fired


class QualityGate:
    """Stateless gate; one instance per batch."""

    def __init__(
        self,
        *,
        provider_ranking: dict[str, float] | None = None,
        provider: Any | None = None,
        quality_delta_threshold: float | None = None,
        noop_cosine_threshold: float | None = None,
        stability_threshold: float | None = None,
    ) -> None:
        self.provider_ranking = provider_ranking or {}
        self.provider = provider
        self.quality_delta_threshold = (
            quality_delta_threshold
            if quality_delta_threshold is not None
            else _DEFAULT_QUALITY_DELTA
        )
        self.noop_cosine_threshold = (
            noop_cosine_threshold
            if noop_cosine_threshold is not None
            else _DEFAULT_NOOP_COSINE
        )
        self.stability_threshold = (
            stability_threshold
            if stability_threshold is not None
            else _DEFAULT_STABILITY
        )

    def evaluate(
        self,
        *,
        text: str | None,
        old_vec: np.ndarray | None,
        old_sig: str,
        new_vec: np.ndarray,
        new_sig: str,
    ) -> GateDecision:
        # Gate 0 — no existing vector: accept new.
        if old_vec is None:
            return GateDecision("ACCEPT_NEW", "first_embed", 0.0)

        # Gate 1 — provider-quality ranking.
        old_rank = self.provider_ranking.get(old_sig, 0.5)
        new_rank = self.provider_ranking.get(new_sig, 0.5)
        delta = new_rank - old_rank
        if delta < self.quality_delta_threshold:
            return GateDecision("REJECT", "lower_quality_provider", float(delta))

        # Gate 2 — change detection. Unit-norm vectors ⇒ dot product == cosine.
        # Dimension-mismatch guard: if old and new vectors come from different-
        # dimensioned models (provider upgrade, e.g. 1024→1536), cosine is
        # undefined. In that case the old vector is from a different model
        # entirely — accept the new one immediately. Gate 3's stability check
        # is about the new model's own reproducibility; it adds no value for
        # a cross-provider upgrade.
        if old_vec.shape[0] != new_vec.shape[0]:
            return GateDecision("ACCEPT_NEW", "dimension_upgrade", 0.0)
        cos_new_old = float(np.dot(old_vec, new_vec))
        if cos_new_old > self.noop_cosine_threshold:
            return GateDecision("NOOP", "unchanged", cos_new_old)

        # Gate 3 — stability via same-provider re-sample.
        if self.provider is not None and text:
            try:
                sample2 = self.provider.embed_single(text)
            except Exception as exc:
                logger.debug("Gate 3 stability sample failed: %s", exc)
                # If we cannot verify stability, accept rather than block; the
                # audit / bake-off will catch regressions later.
                return GateDecision("REPLACE", "passed_without_stability_check", float(delta))
            if sample2.shape[0] != new_vec.shape[0]:
                return GateDecision(
                    "REJECT", "stability_dimension_mismatch", float(delta)
                )
            stability = float(np.dot(new_vec, sample2))
            if stability < self.stability_threshold:
                return GateDecision("REJECT", "unstable_new_vector", stability)

        return GateDecision("REPLACE", "passed_all_gates", float(delta))


# ---------------------------------------------------------------------------
# Configuration loaders
# ---------------------------------------------------------------------------


def load_provider_ranking() -> dict[str, float]:
    """Read the current provider quality ranking from AppSetting.

    Populated by the bake-off task (plan Part 4). Format: JSON object mapping
    ``signature`` -> NDCG@10 normalised to [0, 1]. Returns ``{}`` when no
    bake-off has run — the gate then behaves as ``delta == 0.0`` for all pairs.
    """
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key="embedding.provider_ranking_json").first()
        if row and row.value:
            parsed = json.loads(row.value)
            if isinstance(parsed, dict):
                return {str(k): float(v) for k, v in parsed.items()}
    except Exception:
        logger.debug("provider_ranking load failed; default to empty", exc_info=True)
    return {}


def load_gate_thresholds() -> tuple[float, float, float]:
    """Return ``(quality_delta, noop_cosine, stability)`` from AppSettings."""
    def _f(key: str, fallback: float) -> float:
        try:
            from apps.core.models import AppSetting

            row = AppSetting.objects.filter(key=key).first()
            if row and row.value not in ("", None):
                return float(row.value)
        except Exception:
            pass
        return fallback

    return (
        _f("embedding.gate_quality_delta_threshold", _DEFAULT_QUALITY_DELTA),
        _f("embedding.gate_noop_cosine_threshold", _DEFAULT_NOOP_COSINE),
        _f("embedding.gate_stability_threshold", _DEFAULT_STABILITY),
    )


def is_gate_enabled() -> bool:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key="embedding.gate_enabled").first()
        if row and str(row.value).lower() in ("false", "0", "no", "off"):
            return False
    except Exception:
        pass
    return True


# ---------------------------------------------------------------------------
# Bulk logging helper
# ---------------------------------------------------------------------------


def persist_decisions(
    decisions: list[tuple[int, str, GateDecision, str, str]],
) -> None:
    """Bulk-create ``EmbeddingGateDecision`` rows.

    Args:
        decisions: List of ``(item_id, item_kind, decision, old_sig, new_sig)``.
    """
    if not decisions:
        return
    try:
        from apps.pipeline.models import EmbeddingGateDecision

        rows = [
            EmbeddingGateDecision(
                item_id=item_id,
                item_kind=item_kind,
                old_signature=old_sig or "",
                new_signature=new_sig or "",
                action=decision.action,
                reason=decision.reason,
                score_delta=decision.score_delta,
            )
            for item_id, item_kind, decision, old_sig, new_sig in decisions
        ]
        EmbeddingGateDecision.objects.bulk_create(rows, batch_size=500)
    except Exception:
        logger.warning("EmbeddingGateDecision bulk_create failed", exc_info=True)


__all__ = [
    "GateDecision",
    "QualityGate",
    "is_gate_enabled",
    "load_gate_thresholds",
    "load_provider_ranking",
    "persist_decisions",
]
