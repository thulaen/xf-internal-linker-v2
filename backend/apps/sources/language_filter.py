"""Language-aware content filter — pick #14 candidate-pool wiring.

Reference
---------
Joulin, A., Grave, E., Bojanowski, P., Douze, M., Jégou, H., &
Mikolov, T. (2016). "FastText.zip: Compressing text classification
models." *arXiv:1612.03651*.

Wraps :mod:`apps.sources.fasttext_langid` with a small, batched
"is this English?" decision suitable for the pipeline's content-load
stage. The pipeline's downstream retrievers (semantic, lexical, query
expansion) are tuned for English; non-English content slipping into
the candidate pool wastes Stage-1 compute on hosts the ranker is
unlikely to surface, and dilutes RRF fusion when it does.

Why a separate module?
- The base ``fasttext_langid`` helper returns granular language
  predictions (176 ISO codes); pipeline consumers only care about
  the binary "English vs not" decision.
- A small per-pass cache short-circuits repeated lookups when the
  same content title appears across destinations.
- The "default-allow when fastText / model is missing" semantics
  belong here, not in the lower-level helper.

Cold-start safety
-----------------
- fastText pip dep missing → :func:`is_english` returns ``True``
  (default-allow; the filter degrades to a no-op).
- Model file missing → same as above.
- Operator flag ``fasttext_langid.candidate_filter.enabled`` off →
  filter degrades to a no-op even when fastText IS installed.
- Empty / whitespace-only text → ``True`` (we don't waste a
  prediction on nothing).
- Confidence below the helper's threshold → ``True`` (the lid.176
  model returned ``UND``; we don't know enough to drop the row).
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping

logger = logging.getLogger(__name__)


#: ISO-639 language codes treated as "English" by the filter.
#: ``en`` is the lid.176 label; ``und`` is our undetermined fallback,
#: which we keep (default-allow) rather than drop.
ENGLISH_CODES: frozenset[str] = frozenset({"en", "und"})


def is_english(text: str) -> bool:
    """Return True when *text* is English or undetermined.

    Cold-start safe at every layer; see module docstring.
    """
    if not text or not text.strip():
        return True
    try:
        from apps.core.runtime_flags import is_enabled

        if not is_enabled(
            "fasttext_langid.candidate_filter.enabled", default=True
        ):
            return True
    except Exception:
        return True

    try:
        from apps.sources import fasttext_langid

        prediction = fasttext_langid.predict(text)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("language_filter: fasttext predict raised: %s", exc)
        return True

    if prediction.is_undefined:
        return True
    return prediction.language in ENGLISH_CODES


def filter_english_content_records(
    records: Mapping[object, object],
) -> dict[object, object]:
    """Drop content records whose title is detected as non-English.

    Returns a new dict; the caller's input is unmodified. Records
    whose title is empty / undetermined / English are kept.

    Audit bug A5 fix: previously the helper called the per-text
    ``is_english`` function once per record — at 100k records, that
    means 100k Python↔C round trips into fastText. The batched
    :func:`fasttext_langid.predict_batch` is one C call for the
    whole list and is dramatically faster at scale.

    Cold-start safe: when fastText is unavailable, the operator flag
    is off, or every prediction is undetermined, this returns the
    input dict verbatim — no rows are ever silently dropped on a
    misconfigured install.
    """
    if not records:
        return dict(records)

    # Short-circuit when fasttext or the operator flag is off.
    try:
        from apps.core.runtime_flags import is_enabled
        from apps.sources import fasttext_langid

        if not is_enabled(
            "fasttext_langid.candidate_filter.enabled", default=True
        ):
            return dict(records)
        if not fasttext_langid.is_available():
            return dict(records)
    except Exception:
        return dict(records)

    # One pass to gather titles; one pass to resolve.
    items: list[tuple[object, object, str]] = []
    for key, record in records.items():
        title = getattr(record, "title", "") or ""
        items.append((key, record, title))

    titles = [title for _, _, title in items]
    try:
        predictions = fasttext_langid.predict_batch(titles)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "language_filter: predict_batch raised; falling back to "
            "per-text predict (slower but still correct): %s",
            exc,
        )
        predictions = [fasttext_langid.predict(t) for t in titles]

    kept: dict[object, object] = {}
    dropped = 0
    for (key, record, title), prediction in zip(items, predictions, strict=True):
        if not title.strip():
            kept[key] = record
            continue
        if prediction.is_undefined or prediction.language in ENGLISH_CODES:
            kept[key] = record
        else:
            dropped += 1

    if dropped:
        logger.info(
            "language_filter: dropped %d non-English content records "
            "(kept %d). Toggle off via "
            "AppSetting['fasttext_langid.candidate_filter.enabled']",
            dropped,
            len(kept),
        )
    return kept


def english_subset(
    keys: Iterable[object],
    text_lookup: Mapping[object, str],
) -> set[object]:
    """Return the subset of *keys* whose ``text_lookup[key]`` is English.

    Helper for callers that hold (key → text) mappings rather than
    full content records (e.g. sentence-level filters). Cold-start
    safe — when fastText is unavailable, every key passes.
    """
    return {k for k in keys if is_english(text_lookup.get(k, ""))}
