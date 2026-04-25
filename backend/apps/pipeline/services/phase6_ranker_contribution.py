"""Phase 6 ranker-time contribution dispatcher.

The Wire phase (commit `66a9137`) installed all 10 Phase 6 helpers but
left them disconnected from per-Suggestion scoring — the senior-dev
review correctly flagged this as the largest remaining gap. This
module is the thin bridge: a dispatcher in the style of
:class:`apps.pipeline.services.graph_signal_ranker.GraphSignalRanker`,
applied as a sidecar additive contribution to ``score_final``.

Six ranker-time picks are wired here (paper-backed defaults all live
in :mod:`apps.suggestions.recommended_weights`):

============  ========================================  ====================
Pick          Reference                                 Default weight
============  ========================================  ====================
VADER #22     Hutto & Gilbert 2014 ICWSM §3-4           0.05
KenLM #23     Heafield 2011 WMT §4 trigram fluency      0.05
LDA #18       Blei, Ng & Jordan 2003 JMLR §6 IR         0.10
Node2Vec #37  Grover & Leskovec 2016 KDD §4 cosine sim  0.05
BPR #38       Rendle et al. 2009 UAI §5 Table 2         0.05
FM #39        Rendle 2010 ICDM §3 feature interactions  0.10
============  ========================================  ====================

Every adapter normalises to roughly [-1, +1] before the dispatcher
multiplies by the weight, so the operator-tunable weights have
predictable meaning regardless of which underlying helper produced
the value.

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

This module is Pattern A for ranker-time Phase 6 picks. Each adapter
takes an :class:`AdapterContext` (host sentence text, destination
title, host/destination ContentKey tuples) and returns a float in
roughly [-1, +1]. The dispatcher sums the active contributions per
candidate.

Cold-start safety
-----------------
Returns 0.0 contribution when:

- The pick's ``*.enabled`` AppSetting flag is off.
- The pick's ``*.ranking_weight`` is 0.0.
- The underlying helper module is missing its pip dep.
- The trained model file (LDA / KenLM / Node2Vec / BPR / FM) doesn't
  exist yet — the W1 training jobs populate them on cadence.
- The input text / IDs are empty.
- Any unexpected error is raised by the helper (logged at WARN).

The recommended-preset weights (above) are all small enough that
turning every pick on out-of-the-box won't dominate the existing
15-component composite. Sum of the six weights is **0.40** — well
under the typical 1.0 magnitude of the composite, so the existing
behaviour stays the principal contributor while these signals fine-
tune the ordering.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Callable, Mapping

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Adapter context & signature
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AdapterContext:
    """All inputs an adapter might need, bundled in one immutable record.

    Adapters pick whichever fields they consume:

    - VADER, KenLM → host_sentence_text only.
    - LDA → host_sentence_text + destination_text (cosine over topic
      mixtures of each tokenised text).
    - Node2Vec, BPR → host_key + destination_key (graph node IDs).
    - FM → all four (text features + ID features for one-hot
      vectorisation).
    """

    host_sentence_text: str = ""
    destination_text: str = ""
    host_key: tuple[int, str] | None = None
    destination_key: tuple[int, str] | None = None


#: Callable signature each adapter satisfies.
Adapter = Callable[[AdapterContext], float]


# ─────────────────────────────────────────────────────────────────────
# Concrete adapters
#
# Every adapter:
#  - Returns 0.0 on any cold-start path so the ranker stays stable.
#  - Maps the helper's native output into roughly [-1, +1].
#  - Cites its paper section in the docstring so the math is auditable.
# ─────────────────────────────────────────────────────────────────────


def _vader_adapter(ctx: AdapterContext) -> float:
    """VADER #22 — host-sentence sentiment (Hutto & Gilbert 2014 ICWSM §3-4).

    The compound score from ``apps.sources.vader_sentiment.score`` is
    already calibrated to [-1, +1] (Hutto-Gilbert §3.2), so the
    adapter returns it as-is. Negative → host sentence reads as
    negative; positive → reads as positive. Destination text is
    irrelevant (sentiment is a property of the host context).
    """
    if not ctx.host_sentence_text:
        return 0.0
    try:
        from apps.sources import vader_sentiment

        return float(vader_sentiment.score(ctx.host_sentence_text).compound)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("phase6 vader adapter failed: %s", exc)
        return 0.0


def _kenlm_adapter(ctx: AdapterContext) -> float:
    """KenLM #23 — host-sentence fluency (Heafield 2011 WMT §4).

    KenLM's per-token log10 probability for natural English is
    typically -2 to -4 (Heafield 2011 §4 KneserNey trigram on
    Gigaword). Using ``tanh((per_token + 3) / 1.0)`` centres the
    response around per_token = -3 and saturates smoothly:

    - per_token = -2 (very fluent) → tanh(+1) ≈ +0.76
    - per_token = -3 (typical) → tanh(0) = 0.0 (neutral)
    - per_token = -5 (rare / odd) → tanh(-2) ≈ -0.96

    A fluent host sentence is a better link target than a gibberish
    one, so a positive contribution boosts fluent hosts, negative
    demotes broken ones. Cold-start safe: when no trained ARPA file
    exists yet, ``score_fluency`` returns the neutral score and this
    adapter returns 0.0.
    """
    if not ctx.host_sentence_text:
        return 0.0
    try:
        from apps.pipeline.services import kenlm_fluency

        score = kenlm_fluency.score_fluency(ctx.host_sentence_text)
        if score.token_count == 0:
            return 0.0
        # tanh(x) maps R → (-1, +1); centring at per_token = -3 makes
        # "typical English" the neutral case and "very fluent" / "very
        # rare" both saturate at ~ ±0.95.
        return float(math.tanh(score.per_token + 3.0))
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("phase6 kenlm adapter failed: %s", exc)
        return 0.0


def _lda_adapter(ctx: AdapterContext) -> float:
    """LDA #18 — host/destination topic similarity (Blei-Ng-Jordan 2003 §6).

    Tokenises both texts (lowercase split on whitespace; this is the
    same minimal tokenisation the Phase 6 LDA W1 trainer uses for
    inference inputs), infers each topic distribution, then returns
    the cosine similarity centred around 0.5. The cosine of two
    Dirichlet draws is in [0, 1]; we shift to [-0.5, +0.5] so the
    contribution is symmetric around "no signal".

    Blei-Ng-Jordan 2003 §6 ("Document Modeling — IR experiments")
    shows topic-distribution similarity beats raw bag-of-words for
    document classification — that's the rationale for using it as a
    ranking feature.

    Cold-start safe: an un-trained model returns
    :data:`EMPTY_DISTRIBUTION`; this adapter returns 0.0 in that case.
    """
    if not ctx.host_sentence_text or not ctx.destination_text:
        return 0.0
    try:
        from apps.pipeline.services import lda_topics

        host_tokens = ctx.host_sentence_text.lower().split()
        dest_tokens = ctx.destination_text.lower().split()
        host_dist = lda_topics.infer_topics(host_tokens)
        dest_dist = lda_topics.infer_topics(dest_tokens)
        if host_dist.is_empty or dest_dist.is_empty:
            return 0.0
        return _cosine_minus_half(host_dist.weights, dest_dist.weights)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("phase6 lda adapter failed: %s", exc)
        return 0.0


def _node2vec_adapter(ctx: AdapterContext) -> float:
    """Node2Vec #37 — host/destination graph affinity (Grover-Leskovec 2016 §4).

    Looks up each ContentItem's persisted embedding and returns the
    cosine similarity. Embeddings are L2-normalisable and the cosine
    is in [-1, +1]; we return it directly (the dispatcher's weight
    decides how much it counts).

    Grover-Leskovec 2016 KDD §4 "Experiments" reports cosine
    similarity over Node2Vec walks recovers known link communities
    on Wikipedia and PPI — directly applicable to "is this internal
    link likely to be in the same community as the host sentence?".

    Cold-start safe: when ``vector_for(...)`` returns ``None`` (no
    persisted embedding for that node), the adapter returns 0.0.
    """
    if ctx.host_key is None or ctx.destination_key is None:
        return 0.0
    try:
        from apps.pipeline.services import node2vec_embeddings

        # The W1 trainer stores nodes as ``str(NodeKey)`` where
        # NodeKey = (pk, content_type) — see
        # ``apps.scheduled_updates.jobs.run_node2vec_walks``.
        host_id = str(ctx.host_key)
        dest_id = str(ctx.destination_key)
        host_vec = node2vec_embeddings.vector_for(host_id)
        dest_vec = node2vec_embeddings.vector_for(dest_id)
        if host_vec is None or dest_vec is None:
            return 0.0
        return _cosine_dense(host_vec, dest_vec)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("phase6 node2vec adapter failed: %s", exc)
        return 0.0


def _bpr_adapter(ctx: AdapterContext) -> float:
    """BPR #38 — host-as-user pairwise ranking (Rendle et al. 2009 UAI §5).

    Treats ``host_key`` as the "user" and ``destination_key`` as the
    "item" — a clean reduction of the personalised-LTR setup to the
    internal-linker setting. ``score_for_user`` returns the dot
    product of the user's latent factor and the item's latent factor,
    which can be any real number; we normalise via
    ``tanh(score / 2.0)`` so the output stays in (-1, +1) regardless
    of the BPR factor magnitudes.

    Cold-start safe: returns 0.0 until the W1 ``bpr_refit`` job has
    enough operator approve/reject feedback to fit a model (~5+
    interactions per the helper's own threshold).
    """
    if ctx.host_key is None or ctx.destination_key is None:
        return 0.0
    try:
        from apps.pipeline.services import bpr_ranking

        host_id = str(ctx.host_key)
        dest_id = str(ctx.destination_key)
        scores = bpr_ranking.score_for_user(host_id, [dest_id])
        if scores is None or dest_id not in scores:
            return 0.0
        return float(math.tanh(scores[dest_id] / 2.0))
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("phase6 bpr adapter failed: %s", exc)
        return 0.0


def _fm_adapter(ctx: AdapterContext) -> float:
    """FM #39 — feature-cross score (Rendle 2010 ICDM §3 eq. 1-3).

    Encodes the four context fields as a sparse feature dict —
    matching the schema the W1 ``factorization_machines_refit`` job
    uses when it trains on past Suggestion features — and asks the
    persisted FM model to score it. Output is normalised via
    ``tanh(prediction)`` so the contribution stays in (-1, +1).

    Cold-start safe: returns 0.0 when no trained model exists. The
    feature dict mirrors the trainer's vocabulary so the
    DictVectorizer doesn't drop everything.
    """
    if not (ctx.host_sentence_text or ctx.host_key):
        return 0.0
    try:
        from apps.pipeline.services import factorization_machines

        features = {
            "host_text_len": float(len(ctx.host_sentence_text)),
            "destination_text_len": float(len(ctx.destination_text)),
        }
        if ctx.host_key is not None:
            features[f"host_key:{ctx.host_key[0]}:{ctx.host_key[1]}"] = 1.0
        if ctx.destination_key is not None:
            features[
                f"destination_key:{ctx.destination_key[0]}:{ctx.destination_key[1]}"
            ] = 1.0
        preds = factorization_machines.predict([features])
        if preds is None or not preds:
            return 0.0
        return float(math.tanh(float(preds[0])))
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("phase6 fm adapter failed: %s", exc)
        return 0.0


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _cosine_minus_half(
    a_pairs: list[tuple[int, float]],
    b_pairs: list[tuple[int, float]],
) -> float:
    """Cosine similarity over sparse (topic_id, prob) pairs, shifted to
    [-0.5, +0.5]. Returns 0.0 when either side has zero magnitude.
    """
    if not a_pairs or not b_pairs:
        return 0.0
    a_dict = dict(a_pairs)
    b_dict = dict(b_pairs)
    keys = a_dict.keys() & b_dict.keys()
    if not keys:
        return -0.5  # full mismatch
    dot = sum(a_dict[k] * b_dict[k] for k in keys)
    norm_a = math.sqrt(sum(v * v for v in a_dict.values()))
    norm_b = math.sqrt(sum(v * v for v in b_dict.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    cosine = dot / (norm_a * norm_b)
    # Cosine of non-negative vectors is in [0, 1]; centring at 0.5 makes
    # "typical similarity" the neutral case.
    return float(cosine - 0.5)


def _cosine_dense(a: list[float], b: list[float]) -> float:
    """Cosine similarity over two equal-length dense float lists."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (math.sqrt(norm_a) * math.sqrt(norm_b)))


# ─────────────────────────────────────────────────────────────────────
# Adapter registry
# ─────────────────────────────────────────────────────────────────────


#: Pick name → adapter. Keep the ``ranking_weight`` AppSetting key
#: derivable from the name (``<key>.ranking_weight``) so the
#: dispatcher loads weights with one ``filter(key__in=...)`` query.
_ADAPTERS: dict[str, Adapter] = {
    "vader_sentiment": _vader_adapter,
    "kenlm": _kenlm_adapter,
    "lda": _lda_adapter,
    "node2vec": _node2vec_adapter,
    "bpr": _bpr_adapter,
    "factorization_machines": _fm_adapter,
}


# ─────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Phase6RankerContribution:
    """Bundle of (pick_name, ranking_weight) entries.

    Construct via :func:`build_phase6_contribution` so cold-start,
    disabled flags, and zero weights are all handled in one place.
    The :meth:`contribute_total` method is the only thing the live
    ranker needs to call per (host_sentence, destination) candidate.
    """

    weights: Mapping[str, float] = field(default_factory=dict)

    def contribute_total(self, ctx: AdapterContext) -> float:
        """Return the sum of ``weight × adapter(ctx)`` over picks.

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
                raw = adapter(ctx)
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(
                    "phase6_ranker_contribution: adapter %s raised: %s",
                    pick_name,
                    exc,
                )
                continue
            total += float(weight) * float(raw)
        return total

    def per_pick_breakdown(self, ctx: AdapterContext) -> dict[str, float]:
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
                out[pick_name] = float(adapter(ctx))
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
    """Read ``<pick>.ranking_weight`` from AppSetting.

    Defaults to 0.0 when the row is missing or malformed. The
    Recommended preset (and the corresponding seed migration)
    populate paper-backed defaults so new installs are non-zero out
    of the box; this fallback only matters for partial / legacy
    installs.
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
      via the caller's settings reader), or
    - every adapter is disabled or has a zero ranking_weight.

    Returning ``None`` lets the ranker short-circuit cleanly with
    ``if contribution is None: skip`` — same shape as
    :class:`graph_signal_ranker.GraphSignalRanker`.

    The returned dispatcher is cheap to call per-candidate (six
    dict lookups + the active adapters' work) but ``None`` is even
    cheaper, so the cold-start path is byte-stable with the pre-
    Phase 6 ranker.
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
