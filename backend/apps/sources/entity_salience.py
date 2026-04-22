"""Feature-based entity salience scoring.

Reference: Gamon, Yano, Song, Apacible & Pantel (2013). "Identifying
salient entities in web pages." *Proceedings of the 22nd ACM CIKM*,
pp. 2375-2380.

Goal: given the NER entities spaCy extracts from a document, assign
each a salience score so the ranker can weight matches on the
genuinely-central entities (the ones the document is *about*) more
heavily than mentions that happen to land in the footer or a passing
reference.

Gamon et al. train a gradient-boosted tree over ~40 features; that's
overkill for our use case and adds a model-artefact dependency. This
module implements a **pure-feature heuristic** using the subset they
showed was most predictive (Table 2 of the paper):

- **First-position bonus** — how early does the entity first appear
  in the document? Earlier = more salient.
- **Mention frequency** — number of mentions (title-normalised).
- **Sentence coverage** — fraction of sentences that contain at
  least one mention.
- **Title match** — does the entity appear in the title (if
  provided)?

Output is a salience score in [0, 1], computed as a weighted sum
of the features after min-max normalisation within the document.
Callers can surface the top-k entities to the ranker or the
review UI.

**No model artefact.** No training. No external deps beyond spaCy —
and this module accepts spaCy ``Doc`` objects rather than importing
spaCy itself, so tests can stub the input with a minimal fake. That
matches the pattern used in :mod:`apps.pipeline.services.sentence_splitter`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


#: Default feature weights — tuned by the 4:2:2:2 priority split
#: Gamon et al. report in §4.1 (first-position weighs roughly double
#: the others).
DEFAULT_WEIGHTS: dict[str, float] = {
    "first_position": 0.4,
    "mention_frequency": 0.2,
    "sentence_coverage": 0.2,
    "title_match": 0.2,
}


# ── Protocols (so tests don't need real spaCy Doc objects) ──────────


class _Span(Protocol):
    """Minimal spaCy ``Span`` interface we rely on."""

    text: str
    label_: str
    start_char: int
    end_char: int


class _Sent(Protocol):
    text: str
    start_char: int
    end_char: int


class _Doc(Protocol):
    text: str
    ents: Iterable[_Span]
    sents: Iterable[_Sent]


# ── Public output ──────────────────────────────────────────────────


@dataclass(frozen=True)
class EntitySalience:
    """Scored entity mention cluster (all spans of the same surface form)."""

    text: str
    label: str                 # spaCy entity label, e.g. "PERSON" or "ORG"
    mention_count: int
    first_offset: int          # earliest char offset of any mention
    salience: float            # 0.0–1.0, higher = more central

    # Individual feature values (pre-weighting) — retained for
    # operators who want to inspect why an entity scored the way
    # it did.
    first_position_feature: float
    frequency_feature: float
    coverage_feature: float
    title_feature: float


# ── Public API ──────────────────────────────────────────────────────


def rank_entities(
    doc: _Doc,
    *,
    title: str | None = None,
    top_k: int | None = None,
    weights: dict[str, float] | None = None,
    min_mention_count: int = 1,
) -> list[EntitySalience]:
    """Return entities of *doc* ranked by salience, most salient first.

    Parameters
    ----------
    doc
        A spaCy-like ``Doc``. See the ``_Doc`` protocol for the
        minimum surface needed (``.text``, ``.ents``, ``.sents``).
    title
        Optional page/post title. When provided, the title-match
        feature credits entities whose normalised text appears in
        the title.
    top_k
        If set, truncates the result.
    weights
        Override :data:`DEFAULT_WEIGHTS`. Must contain keys
        ``first_position``, ``mention_frequency``, ``sentence_coverage``,
        ``title_match``. Extra keys are ignored; missing keys default
        to the built-in value.
    min_mention_count
        Entities with fewer mentions than this are dropped before
        scoring (saves feature work on spurious ents).
    """
    final_weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    doc_text = doc.text or ""
    doc_len = max(1, len(doc_text))
    sentences = list(doc.sents)
    sentence_count = max(1, len(sentences))
    title_normalised = _normalise(title) if title else ""

    # First-pass aggregation by (normalised text, label).
    buckets: dict[tuple[str, str], dict[str, object]] = {}
    for ent in doc.ents:
        key = (_normalise(ent.text), ent.label_)
        if not key[0]:
            continue
        bucket = buckets.setdefault(
            key,
            {
                "display": ent.text,
                "mention_count": 0,
                "first_offset": ent.start_char,
                "sentence_indices": set(),
            },
        )
        bucket["mention_count"] = int(bucket["mention_count"]) + 1  # type: ignore[operator]
        if ent.start_char < int(bucket["first_offset"]):  # type: ignore[arg-type]
            bucket["first_offset"] = ent.start_char
        bucket["sentence_indices"].add(  # type: ignore[union-attr]
            _sentence_index_for_offset(ent.start_char, sentences)
        )

    if not buckets:
        return []

    # Second pass: materialise features + score.
    scored: list[EntitySalience] = []
    max_frequency = max(int(b["mention_count"]) for b in buckets.values())  # type: ignore[arg-type]
    for (norm_text, label), bucket in buckets.items():
        mention_count = int(bucket["mention_count"])  # type: ignore[arg-type]
        if mention_count < min_mention_count:
            continue
        first_offset = int(bucket["first_offset"])  # type: ignore[arg-type]

        # Feature: first-position bonus. Earlier = higher score.
        # Normalised so the very first char of the doc returns 1.0
        # and the very last char returns 0.0.
        first_position = max(0.0, 1.0 - (first_offset / doc_len))

        # Feature: mention frequency — min-max over the doc.
        frequency = (
            mention_count / max_frequency if max_frequency > 0 else 0.0
        )

        # Feature: sentence coverage.
        coverage = (
            len(bucket["sentence_indices"]) / sentence_count  # type: ignore[arg-type]
        )

        # Feature: title match.
        title_match = (
            1.0 if title_normalised and norm_text in title_normalised else 0.0
        )

        salience = (
            final_weights["first_position"] * first_position
            + final_weights["mention_frequency"] * frequency
            + final_weights["sentence_coverage"] * coverage
            + final_weights["title_match"] * title_match
        )
        # Clamp — weights may sum to >1 if operator overrode defaults.
        salience = max(0.0, min(1.0, salience))

        scored.append(
            EntitySalience(
                text=str(bucket["display"]),
                label=label,
                mention_count=mention_count,
                first_offset=first_offset,
                salience=salience,
                first_position_feature=first_position,
                frequency_feature=frequency,
                coverage_feature=coverage,
                title_feature=title_match,
            )
        )

    scored.sort(key=lambda e: (-e.salience, -e.mention_count, e.first_offset))
    if top_k is not None and top_k >= 0:
        scored = scored[:top_k]
    return scored


# ── Internals ──────────────────────────────────────────────────────


def _normalise(text: str) -> str:
    """Light normalisation for comparison — lowercase + strip."""
    return (text or "").strip().lower()


def _sentence_index_for_offset(offset: int, sentences: list[_Sent]) -> int:
    """Return the 0-based sentence index that contains *offset*.

    Falls back to the nearest preceding sentence when ``offset``
    lands in whitespace between sentences. Returns 0 when
    sentences is empty.
    """
    if not sentences:
        return 0
    for idx, sent in enumerate(sentences):
        if sent.start_char <= offset < sent.end_char:
            return idx
    # Past the last sentence — bucket with the last.
    return len(sentences) - 1
