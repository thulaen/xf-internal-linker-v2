"""Graph-signal store for HITS / PPR / TrustRank — picks #29, #36, #30.

The W1 scheduled jobs ``hits_refresh``,
``personalized_pagerank_refresh``, and ``trustrank_propagation``
compute per-node scores but currently throw them away. W3c adds the
persistence + read layer so the ranker (and any other consumer) can
look up a destination's authority / topical-PPR / trust score in
O(1).

Design choice: top-N AppSetting JSON, not new ContentItem columns.

Reasons:

- A migration adding 6+ FloatField columns to ContentItem
  (HITS authority, HITS hub, PPR, TrustRank, plus future Node2Vec
  vectors) would be risky on a populated production DB.
- The ranker only needs scores for the **best** destinations per
  signal — the long tail at score ≈ 0 doesn't influence a top-K
  ranking. Keeping the top-N (default 10 000) per signal keeps the
  AppSetting payload at ~200 KB per key, well under Django's
  practical TextField ceiling.
- AppSetting reads are cached; a typical ranker request reads the
  store once per pipeline run, not per candidate.

Format on disk: ``AppSetting[graph_signals.<signal>].value`` is a
JSON object mapping ``"<pk>:<content_type>"`` → score (float).
``"<pk>:<content_type>"`` is the same ``ContentKey`` shape used
elsewhere in the ranking pipeline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Hashable, Mapping

logger = logging.getLogger(__name__)


#: Default top-N kept per signal. Tuned to stay under the practical
#: AppSetting ceiling (~200 KB JSON for 10k entries × ~20 bytes each).
DEFAULT_TOP_N: int = 10_000

#: Neutral fallback when a node hasn't been scored yet (cold start
#: or it's outside the top-N). 0.5 is the project-wide convention
#: for "no signal" rather than 0.0.
NEUTRAL_SCORE: float = 0.5


SIGNAL_HITS_AUTHORITY = "hits_authority"
SIGNAL_HITS_HUB = "hits_hub"
SIGNAL_PPR = "personalized_pagerank"
SIGNAL_TRUSTRANK = "trustrank"

#: AppSetting key template — ``graph_signals.<signal>``.
KEY_TEMPLATE = "graph_signals.{signal}"
KEY_FITTED_AT_TEMPLATE = "graph_signals.{signal}.fitted_at"
KEY_NODE_COUNT_TEMPLATE = "graph_signals.{signal}.node_count"


@dataclass(frozen=True)
class GraphSignalSnapshot:
    """Per-signal score table loaded from AppSetting."""

    signal: str
    scores: dict[str, float]
    fitted_at: str | None
    full_node_count: int

    def lookup(self, key: Hashable) -> float:
        """Return the persisted score for *key*, or ``NEUTRAL_SCORE``."""
        token = _key_to_token(key)
        return self.scores.get(token, NEUTRAL_SCORE)


# ── Read API ──────────────────────────────────────────────────────


def load_snapshot(signal: str) -> GraphSignalSnapshot | None:
    """Return the persisted snapshot for *signal*, or ``None`` on cold start."""
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return None

    rows = dict(
        AppSetting.objects.filter(
            key__in=[
                KEY_TEMPLATE.format(signal=signal),
                KEY_FITTED_AT_TEMPLATE.format(signal=signal),
                KEY_NODE_COUNT_TEMPLATE.format(signal=signal),
            ]
        ).values_list("key", "value")
    )
    raw = rows.get(KEY_TEMPLATE.format(signal=signal))
    if not raw:
        return None
    try:
        scores = json.loads(raw)
    except ValueError:
        logger.warning(
            "graph_signal_store: malformed JSON for signal %s, ignoring", signal
        )
        return None
    if not isinstance(scores, dict):
        return None
    try:
        full_count = int(
            rows.get(KEY_NODE_COUNT_TEMPLATE.format(signal=signal), "0") or "0"
        )
    except (TypeError, ValueError):
        full_count = 0
    return GraphSignalSnapshot(
        signal=signal,
        scores={str(k): float(v) for k, v in scores.items()},
        fitted_at=rows.get(KEY_FITTED_AT_TEMPLATE.format(signal=signal)),
        full_node_count=full_count,
    )


def score_for(signal: str, key: Hashable) -> float:
    """Return the persisted score for *key* under *signal*, or neutral."""
    snap = load_snapshot(signal)
    if snap is None:
        return NEUTRAL_SCORE
    return snap.lookup(key)


# ── Write API (used by the W1 graph jobs) ────────────────────────


def persist_top_n(
    *,
    signal: str,
    scores: Mapping[Hashable, float],
    top_n: int = DEFAULT_TOP_N,
) -> int:
    """Persist the top-*top_n* scores under ``graph_signals.<signal>``.

    Returns the number of entries actually written. Lower scores are
    silently dropped — they're indistinguishable from neutral for the
    ranker's purposes.
    """
    if not scores:
        # Empty input → wipe the existing snapshot rather than leave
        # stale data in place. Operators see a freshly-rebuilt table.
        return _persist_raw(signal=signal, scores={}, full_node_count=0)

    sorted_pairs = sorted(scores.items(), key=lambda pair: -pair[1])
    capped = sorted_pairs[:top_n]
    serialised = {_key_to_token(k): float(v) for k, v in capped}
    return _persist_raw(
        signal=signal,
        scores=serialised,
        full_node_count=len(scores),
    )


# ── Internals ────────────────────────────────────────────────────


def _key_to_token(key: Hashable) -> str:
    """Coerce a ContentKey-style key to its persisted string form.

    Accepts:
    - ``int`` (legacy single-pk keys) → ``"123"``.
    - ``(pk, content_type)`` tuple → ``"123:thread"``.
    - ``str`` → unchanged (already serialised).
    """
    if isinstance(key, str):
        return key
    if isinstance(key, int):
        return str(key)
    if isinstance(key, tuple) and len(key) == 2:
        pk, content_type = key
        return f"{pk}:{content_type}"
    raise ValueError(
        f"graph_signal_store: cannot tokenise key {key!r} "
        f"(expected int, str, or (pk, content_type) tuple)"
    )


def _persist_raw(
    *, signal: str, scores: dict[str, float], full_node_count: int
) -> int:
    from django.utils import timezone

    from apps.core.models import AppSetting

    key = KEY_TEMPLATE.format(signal=signal)
    fitted_key = KEY_FITTED_AT_TEMPLATE.format(signal=signal)
    count_key = KEY_NODE_COUNT_TEMPLATE.format(signal=signal)
    AppSetting.objects.update_or_create(
        key=key,
        defaults={
            "value": json.dumps(scores, separators=(",", ":")),
            "description": (
                f"Top-N scores for graph signal '{signal}' — refit by "
                "the matching W1 scheduled job; consumed by the ranker."
            ),
        },
    )
    AppSetting.objects.update_or_create(
        key=fitted_key,
        defaults={
            "value": timezone.now().isoformat(),
            "description": f"Last refit timestamp for graph signal '{signal}'.",
        },
    )
    AppSetting.objects.update_or_create(
        key=count_key,
        defaults={
            "value": str(full_node_count),
            "description": (
                f"Total nodes scored before top-N truncation for '{signal}'."
            ),
        },
    )
    return len(scores)
