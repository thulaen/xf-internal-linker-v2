"""Destination distillation: select the most representative sentences from a post.

Scoring heuristic (applied per sentence):
  base_score = 1.0
  + entity_boost     if sentence contains named entities or noun chunks
  + intent_boost     if sentence contains troubleshooting/solution keywords
  * position_decay   exponential penalty based on sentence index (earlier = better)

Top-K sentences (by score) are joined to form the distilled body text.
"""

from __future__ import annotations

import math
import re
from .spacy_loader import get_spacy_nlp

MAX_DISTILLED_SENTENCES = 5
ENTITY_BOOST = 0.4
INTENT_BOOST = 0.3
POSITION_DECAY_LAMBDA = 0.15

_INTENT_WORDS = re.compile(
    r"\b(?:"
    r"fix|solve|resolv|solution|workaround|issue|problem|error|bug|crash"
    r"|install|configur|setup|upgrad|migrat|update|enable|disable"
    r"|how\s+to|step|guide|tutorial|tip|trick|note|warning|important"
    r")\w*\b",
    re.IGNORECASE,
)




def distill_body(sentences: list[str], max_sentences: int = MAX_DISTILLED_SENTENCES) -> str:
    """Score and select the top sentences to represent a destination's body.

    Returns the distilled text as a single joined string.
    """
    if not sentences:
        return ""

    get_spacy_nlp()

    scored: list[tuple[float, int, str]] = []
    for idx, sent in enumerate(sentences):
        score = _score_sentence(sent, idx, len(sentences))
        scored.append((score, idx, sent))

    scored.sort(key=lambda t: (-t[0], t[1]))
    top = scored[:max_sentences]
    top.sort(key=lambda t: t[1])

    return " ".join(t[2] for t in top)


def _score_sentence(sent: str, idx: int, total: int) -> float:
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

    decay = math.exp(-POSITION_DECAY_LAMBDA * idx)
    score *= decay

    return score
