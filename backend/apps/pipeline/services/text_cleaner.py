"""BBCode cleaning and content hashing for imported post text."""

from __future__ import annotations

import hashlib
import re
import string


_QUOTE_RE = re.compile(
    r"\[QUOTE[^\]]*\](?:(?!\[QUOTE).)*?\[/QUOTE\]",
    re.IGNORECASE | re.DOTALL,
)

_CODE_RE = re.compile(
    r"\[CODE[^\]]*\](?:(?!\[CODE).)*?\[/CODE\]",
    re.IGNORECASE | re.DOTALL,
)

_TAG_RE = re.compile(r"\[[^\]]+\]")
_MULTI_WS_RE = re.compile(r"\s+")
_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def clean_bbcode(raw_text: str) -> str:
    """Strip BBCode from raw text, obliterating QUOTE and CODE block contents.

    Returns plain text with normalized whitespace.
    """
    if not raw_text:
        return ""

    text = raw_text
    text = _obliterate_blocks(text, _QUOTE_RE)
    text = _obliterate_blocks(text, _CODE_RE)
    text = _TAG_RE.sub("", text)
    text = _MULTI_WS_RE.sub(" ", text).strip()
    return text


def generate_content_hash(title: str, clean_text: str) -> str:
    """Generate a SHA-256 hash from aggressively normalized title + clean_text."""
    combined = f"{title} {clean_text}"
    normalized = combined.lower()
    normalized = normalized.translate(_PUNCT_TABLE)
    normalized = _MULTI_WS_RE.sub(" ", normalized).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _obliterate_blocks(text: str, pattern: re.Pattern[str]) -> str:
    """Repeatedly apply a block-removal pattern until no matches remain."""
    while True:
        result = pattern.sub("", text)
        if result == text:
            return result
        text = result
