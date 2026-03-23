"""
Sentence splitter service — spaCy-based sentence segmentation.

Splits host thread content into sentences for per-sentence embedding.
Only processes the FIRST 600 WORDS (non-negotiable product rule).

Migrated from V1 with minimal changes in Phase 2.
V1 source: ../xf-internal-linker/services/sentence_splitter.py
"""

from django.conf import settings

# TODO Phase 2: migrate from V1 sentence_splitter.py
# V1 behavior to preserve:
# - Uses spaCy en_core_web_sm for sentence boundaries
# - Truncates to first HOST_SCAN_WORD_LIMIT words before splitting
# - Returns list of (sentence_text, word_offset) tuples


def split_sentences(text: str) -> list[str]:
    """
    Split text into sentences using spaCy, truncating at 600 words.

    Args:
        text: Clean text content (BBCode/HTML already stripped).

    Returns:
        List of sentence strings from the first 600 words only.

    Raises:
        NotImplementedError: Until Phase 2 migration is complete.
    """
    raise NotImplementedError("Sentence splitter service migrated in Phase 2")


def truncate_to_word_limit(text: str, limit: int | None = None) -> str:
    """
    Truncate text to the first N words.

    Args:
        text: Input text.
        limit: Word count limit. Defaults to settings.HOST_SCAN_WORD_LIMIT (600).

    Returns:
        Truncated text string.
    """
    word_limit = limit or getattr(settings, "HOST_SCAN_WORD_LIMIT", 600)
    words = text.split()
    if len(words) <= word_limit:
        return text
    return " ".join(words[:word_limit])
