"""Destination distillation: select the most representative sentences from a post.

Scoring heuristic (applied per sentence):
  base_score = 1.0
  + entity_boost     if sentence contains named entities or noun chunks
  + intent_boost     if sentence contains troubleshooting/solution keywords
  + yake_boost       if sentence contains YAKE-extracted document keywords
  * position_decay   exponential penalty based on sentence index (earlier = better)

The YAKE boost (Campos et al. 2020 *Information Sciences* §3.5) tilts
distillation toward sentences that contain the document's most
salient keywords. YAKE's score is *lower-is-better* so we use the
inverse to compute boost magnitude. Default coefficient = 0.2 keeps
the boost smaller than the entity boost (0.4) since YAKE output can
be noisier on short forum posts.

Top-K sentences (by score) are joined to form the distilled body text.
"""

from __future__ import annotations

import math
import re
from .spacy_loader import get_spacy_nlp

MAX_DISTILLED_SENTENCES = 5
ENTITY_BOOST = 0.4
INTENT_BOOST = 0.3
#: Per-keyword coefficient for the YAKE boost. Bounded above by
#: ``YAKE_BOOST_CAP`` so a sentence packed with keywords can't
#: dominate the entire score.
YAKE_BOOST_PER_KEYWORD = 0.05
YAKE_BOOST_CAP = 0.4
POSITION_DECAY_LAMBDA = 0.15

_INTENT_WORDS = re.compile(
    r"\b(?:"
    r"fix|solve|resolv|solution|workaround|issue|problem|error|bug|crash"
    r"|install|configur|setup|upgrad|migrat|update|enable|disable"
    r"|how\s+to|step|guide|tutorial|tip|trick|note|warning|important"
    r")\w*\b",
    re.IGNORECASE,
)


def distill_body(
    sentences: list[str], max_sentences: int = MAX_DISTILLED_SENTENCES
) -> str:
    """Score and select the top sentences to represent a destination's body.

    Returns the distilled text as a single joined string.
    """
    if not sentences:
        return ""

    get_spacy_nlp()

    # Pick #17 — extract document-level keywords ONCE per call so the
    # per-sentence YAKE boost can match against them. Cold-start safe:
    # when YAKE isn't installed / its toggle is off, ``extract``
    # returns ``[]`` and the boost is a no-op.
    yake_keywords_lower = _yake_keywords_lower(" ".join(sentences))

    scored: list[tuple[float, int, str]] = []
    for idx, sent in enumerate(sentences):
        score = _score_sentence(
            sent, idx, len(sentences), yake_keywords_lower=yake_keywords_lower
        )
        scored.append((score, idx, sent))

    scored.sort(key=lambda t: (-t[0], t[1]))
    top = scored[:max_sentences]
    top.sort(key=lambda t: t[1])

    return " ".join(t[2] for t in top)


def _yake_keywords_lower(document_text: str) -> list[str]:
    """Return the top YAKE keywords for *document_text* in lowercase.

    Cold-start safe at every layer: missing pip dep / disabled
    toggle / empty input → empty list. Lowercased so case-insensitive
    "does the sentence contain this keyword?" comparisons work.
    """
    if not document_text or len(document_text) < 32:
        return []
    try:
        from apps.sources import yake_keywords

        hits = yake_keywords.extract(document_text, top_k=10)
    except Exception:
        return []
    return [hit.keyword.lower() for hit in hits if hit.keyword]


def _score_sentence(
    sent: str,
    idx: int,
    total: int,
    *,
    yake_keywords_lower: list[str] | None = None,
) -> float:
    score = 1.0

    nlp = get_spacy_nlp()
    if nlp is not None:
        doc = nlp(sent)
        if list(doc.ents) or list(doc.noun_chunks):
            score += ENTITY_BOOST
    else:
        if re.search(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", sent):
            score += ENTITY_BOOST

    if _INTENT_WORDS.search(sent):
        score += INTENT_BOOST

    # YAKE boost — count how many top-K document keywords appear in
    # this sentence; multiply by ``YAKE_BOOST_PER_KEYWORD``; cap at
    # ``YAKE_BOOST_CAP`` so a single keyword-heavy sentence can't
    # blow past the entity / intent bonuses.
    if yake_keywords_lower:
        sent_lower = sent.lower()
        matches = sum(1 for kw in yake_keywords_lower if kw in sent_lower)
        if matches:
            score += min(YAKE_BOOST_CAP, matches * YAKE_BOOST_PER_KEYWORD)

    decay = math.exp(-POSITION_DECAY_LAMBDA * idx)
    score *= decay

    return score
