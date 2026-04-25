"""Graph-signal ranker contribution — wires picks #29 / #30 / #36 read APIs into the live ranker.

The W3c slice (commit 47b9659) added a persisted store for HITS authority,
Personalized PageRank, and TrustRank scores — but the live ranker never read
from it. This module is the missing bridge.

Design intent
-------------
Each destination gets a small additive contribution computed as

    Σ over signal s :  weight_s × (score_s(destination) − 0.5)

where ``score_s(destination)`` is the persisted top-N score from
:mod:`apps.pipeline.services.graph_signal_store` (defaulting to the
project-wide neutral baseline of 0.5 when the destination is outside the
top-N or no scheduled refit has run yet).

The 0.5 offset keeps cold-start safe: with no scores persisted yet the
contribution is exactly zero, so flipping ``graph_signals.enabled`` on by
default does not perturb existing rankings until the W1 jobs populate the
store.

Why a dedicated helper rather than expanding the 15-component composite?
------------------------------------------------------------------------
- The graph signals are properties of the **destination node**, not the
  candidate-link pair. They factor cleanly out of the per-sentence loop
  in ``ranker.score_destination_matches`` (one lookup per destination,
  not per match).
- Keeping the contribution out of the C++ batch composite avoids an ABI
  change to ``apps.pipeline.scoring`` and a corresponding rebuild.
- The pattern matches the existing FR-099 / FR-105 dispatcher: load
  caches once, apply additive contribution after the main composite.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Hashable, Mapping

from .graph_signal_store import (
    GraphSignalSnapshot,
    NEUTRAL_SCORE,
    SIGNAL_HITS_AUTHORITY,
    SIGNAL_PPR,
    SIGNAL_TRUSTRANK,
    load_snapshot,
)

logger = logging.getLogger(__name__)


#: Canonical signal names this ranker knows how to read. Order
#: doesn't affect math but is used for stable diagnostics output.
KNOWN_SIGNALS: tuple[str, ...] = (
    SIGNAL_HITS_AUTHORITY,
    SIGNAL_PPR,
    SIGNAL_TRUSTRANK,
)


@dataclass(frozen=True, slots=True)
class GraphSignalRanker:
    """Bundle of (snapshot, weight) pairs ready for per-candidate lookup.

    Construct via :func:`build_graph_signal_ranker` so cold-start, missing
    snapshots, and zero-weight signals are all handled in one place. The
    ``contribution(key)`` method is the only thing the live ranker needs
    to call.
    """

    weights: Mapping[str, float]
    snapshots: Mapping[str, GraphSignalSnapshot] = field(default_factory=dict)

    def contribution(self, key: Hashable) -> float:
        """Return Σ w_s × (score_s(key) − 0.5) for every wired signal.

        Returns ``0.0`` when no signals have non-zero weight or when no
        snapshot is persisted yet — the cold-start path. The 0.5 baseline
        is the project-wide convention for "no signal" (see
        :data:`apps.pipeline.services.graph_signal_store.NEUTRAL_SCORE`).
        """
        total = 0.0
        for signal, weight in self.weights.items():
            if weight == 0.0:
                continue
            snapshot = self.snapshots.get(signal)
            if snapshot is None:
                # No persisted scores yet for this signal — treat as neutral.
                continue
            score = snapshot.lookup(key)
            total += float(weight) * (score - NEUTRAL_SCORE)
        return total

    def per_signal_scores(self, key: Hashable) -> dict[str, float]:
        """Return raw [0, 1] score per signal for diagnostics.

        Diagnostics-only: the live ranker only consumes
        :meth:`contribution`. Useful when an operator wants to surface
        the unweighted authority/PPR/TrustRank values in the Explain
        panel.
        """
        out: dict[str, float] = {}
        for signal in KNOWN_SIGNALS:
            snapshot = self.snapshots.get(signal)
            out[signal] = NEUTRAL_SCORE if snapshot is None else snapshot.lookup(key)
        return out

    @property
    def is_active(self) -> bool:
        """True iff any signal has a non-zero weight AND a snapshot."""
        return any(
            w != 0.0 and self.snapshots.get(s) is not None
            for s, w in self.weights.items()
        )


def build_graph_signal_ranker(
    *,
    weights: Mapping[str, float],
    enabled: bool = True,
    load_snapshot_fn=load_snapshot,
) -> GraphSignalRanker | None:
    """Construct a :class:`GraphSignalRanker` from current settings.

    Returns ``None`` when:

    - the feature is disabled, or
    - every weight is zero (no signal would contribute), or
    - no snapshot is persisted for any non-zero-weight signal.

    Returning ``None`` lets callers short-circuit cleanly with
    ``if ranker is None: skip``.

    The ``load_snapshot_fn`` parameter is dependency-injected so tests can
    stub the AppSetting reads without monkey-patching the module under
    test.
    """
    if not enabled:
        return None

    active_weights = {s: float(w) for s, w in weights.items() if float(w) != 0.0}
    if not active_weights:
        return None

    snapshots: dict[str, GraphSignalSnapshot] = {}
    for signal in active_weights:
        try:
            snap = load_snapshot_fn(signal)
        except Exception:
            logger.debug(
                "graph_signal_ranker: failed to load snapshot for %s — skipping",
                signal,
                exc_info=True,
            )
            continue
        if snap is not None:
            snapshots[signal] = snap

    if not snapshots:
        # Every requested signal is cold — nothing to apply yet.
        return None

    return GraphSignalRanker(weights=active_weights, snapshots=snapshots)
