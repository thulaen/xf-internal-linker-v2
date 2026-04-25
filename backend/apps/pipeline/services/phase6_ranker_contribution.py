"""Phase 6 ranker-time contribution dispatcher.

The Wire phase (commit `66a9137`) installed all 10 Phase 6 helpers but
left them disconnected from per-Suggestion scoring — the senior-dev
review correctly flagged this as the largest remaining gap. This
module is the thin bridge: a dispatcher in the style of
:class:`apps.pipeline.services.graph_signal_ranker.GraphSignalRanker`,
applied as a sidecar additive contribution to ``score_final``.

Design intent
-------------
Two patterns are already proven in this codebase:

- **Pattern A — Sidecar additive contribution.** Used by
  :mod:`graph_signal_ranker` and :mod:`fr099_fr105_signals`. Each
  contribution is computed independently and added to ``score_final``
  outside the C++ batch composite, so the 15-component composite
  ABI doesn't change.
- **Pattern B — Crawler middleware.** Used by source-layer helpers
  like :mod:`sha256_fingerprint` / :mod:`encoding`.

This module is Pattern A for ranker-time Phase 6 picks (VADER #22,
KenLM #23, LDA #18, Node2Vec #37, BPR #38, FM #39). Each pick has
an adapter that reads its own AppSetting toggle / weight; the
dispatcher sums up the active contributions per (host_sentence,
destination) candidate.

Why no per-pick ``score_<pick>`` columns yet
--------------------------------------------
Each new column adds a migration + ScoredCandidate signature change
+ test ripple. Following the FR-099..105 dispatcher's lead means
this module is *additive only* on ``score_final`` — no schema
change is required for the operator to see Phase 6 contributions
take effect.

If a future PR wants per-pick observability (Suggestion.score_vader,
score_kenlm, etc.), it can replace this module's bulk
``contribute_total`` call with a per-pick break-down. The module is
designed so that's a one-file refactor.

Cold-start safety
-----------------
Returns 0.0 contribution when:

- The pick's ``*.enabled`` AppSetting flag is off.
- The pick's ``*.ranking_weight`` is 0.0.
- The underlying helper module is missing its pip dep.
- The input text is empty.
- Any unexpected error is raised by the helper (logged at WARN).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Mapping

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Per-pick adapters — each takes (host_sentence_text, destination_text)
# and returns a [-1.0, +1.0]-ish raw score. The dispatcher multiplies
# by the operator-tunable ``*.ranking_weight`` AppSetting.
# ─────────────────────────────────────────────────────────────────────


def _vader_adapter(host_sentence_text: str, destination_text: str) -> float:
    """VADER #22 — host-sentence sentiment polarity (Hutto-Gilbert 2014).

    Returns the ``compound`` score from ``apps.sources.vader_sentiment``,
    which is already in [-1, +1]. Negative → host sentence sounds
    negative; positive → host sentence sounds positive. ``destination_text``
    is unused for VADER (sentiment is a property of the host context).

    Cold-start safe: VADER returns ``NEUTRAL`` (compound=0.0) when its
    pip dep is missing or its ``vader_sentiment.enabled`` AppSetting
    is off, so this adapter naturally returns 0.0 in either case.
    """
    if not host_sentence_text:
        return 0.0
    try:
        from apps.sources import vader_sentiment

        return float(vader_sentiment.score(host_sentence_text).compound)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("phase6 vader adapter failed: %s", exc)
        return 0.0


#: Callable signature each adapter satisfies.
Adapter = Callable[[str, str], float]


#: Pick name → adapter. Keep the ``ranking_weight`` AppSetting key
#: derivable from the name (``<key>.ranking_weight``) so the
#: dispatcher loads weights with one ``filter(key__in=...)`` query.
_ADAPTERS: dict[str, Adapter] = {
    "vader_sentiment": _vader_adapter,
    # Future picks slot in here. Each adapter takes
    # (host_sentence_text, destination_text) and returns a float.
    # Examples (TODO — separate PRs):
    #   "kenlm": _kenlm_anchor_fluency_adapter,
    #   "lda": _lda_topic_similarity_adapter,
    #   "node2vec": _node2vec_affinity_adapter,
    #   "bpr": _bpr_personalised_adapter,
    #   "factorization_machines": _fm_feature_cross_adapter,
}


# ─────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Phase6RankerContribution:
    """Bundle of (pick_name, ranking_weight, adapter) entries.

    Construct via :func:`build_phase6_contribution` so cold-start,
    disabled flags, and zero weights are all handled in one place.
    The :meth:`contribute_total` method is the only thing the live
    ranker needs to call per (host_sentence, destination) candidate.
    """

    weights: Mapping[str, float] = field(default_factory=dict)

    def contribute_total(
        self,
        *,
        host_sentence_text: str,
        destination_text: str = "",
    ) -> float:
        """Return the sum of ``weight × adapter(host, dest)`` over picks.

        Returns ``0.0`` when no adapters have non-zero weight (the
        ranker becomes a no-op cleanly). One contribution per active
        pick; failures inside an adapter are caught and logged so a
        single broken helper can't poison the entire ranker pass.
        """
        if not self.weights:
            return 0.0
        total = 0.0
        for pick_name, weight in self.weights.items():
            if weight == 0.0:
                continue
            adapter = _ADAPTERS.get(pick_name)
            if adapter is None:
                continue
            try:
                raw = adapter(host_sentence_text, destination_text)
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(
                    "phase6_ranker_contribution: adapter %s raised: %s",
                    pick_name,
                    exc,
                )
                continue
            total += float(weight) * float(raw)
        return total

    def per_pick_breakdown(
        self,
        *,
        host_sentence_text: str,
        destination_text: str = "",
    ) -> dict[str, float]:
        """Return per-pick raw scores (pre-weight) for the Explain panel.

        Diagnostics-only: the live ranker only consumes
        :meth:`contribute_total`. Useful when an operator wants to see
        the unweighted per-pick contribution alongside the blended
        ``score_final``.
        """
        out: dict[str, float] = {}
        for pick_name in self.weights:
            adapter = _ADAPTERS.get(pick_name)
            if adapter is None:
                continue
            try:
                out[pick_name] = float(adapter(host_sentence_text, destination_text))
            except Exception:
                out[pick_name] = 0.0
        return out

    @property
    def is_active(self) -> bool:
        """True iff any pick has a non-zero weight."""
        return any(w != 0.0 for w in self.weights.values())


# ─────────────────────────────────────────────────────────────────────
# Construction
# ─────────────────────────────────────────────────────────────────────


def _read_weight_for(pick_name: str) -> float:
    """Read ``<pick>.ranking_weight`` from AppSetting; default 0.0.

    A 0.0 default means flipping the global ``<pick>.enabled`` flag
    on does NOT auto-perturb the ranker — the operator must
    explicitly raise the weight before the contribution shows up in
    ``score_final``. This is the conservative default the FR-099
    pattern uses.
    """
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(
            key=f"{pick_name}.ranking_weight"
        ).first()
        if row is None or not row.value:
            return 0.0
        return float(row.value)
    except Exception:
        return 0.0


def _is_enabled(pick_name: str) -> bool:
    """Read ``<pick>.enabled`` via :mod:`apps.core.runtime_flags`."""
    try:
        from apps.core.runtime_flags import is_enabled

        return is_enabled(f"{pick_name}.enabled", default=True)
    except Exception:
        return False


def build_phase6_contribution(
    *,
    enabled_global: bool = True,
) -> Phase6RankerContribution | None:
    """Construct the dispatcher from current AppSetting values.

    Returns ``None`` when:

    - ``enabled_global`` is False (operator killswitch — controlled
      via ``phase6_ranker.enabled`` AppSetting in the caller), or
    - every adapter is disabled or has a zero ranking_weight.

    Returning ``None`` lets the ranker short-circuit cleanly with
    ``if contribution is None: skip`` — same shape as
    :class:`graph_signal_ranker.GraphSignalRanker`.
    """
    if not enabled_global:
        return None
    weights: dict[str, float] = {}
    for pick_name in _ADAPTERS:
        if not _is_enabled(pick_name):
            continue
        weight = _read_weight_for(pick_name)
        if weight == 0.0:
            continue
        weights[pick_name] = weight
    if not weights:
        return None
    return Phase6RankerContribution(weights=weights)
