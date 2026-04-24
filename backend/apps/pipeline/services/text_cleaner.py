"""Text cleaning and content hashing for imported post text."""

from __future__ import annotations

import hashlib
from html import unescape
import re
import string

from django.utils.html import strip_tags


_QUOTE_RE = re.compile(
    r"\[QUOTE[^\]]*\](?:(?!\[QUOTE).)*?\[/QUOTE\]",
    re.IGNORECASE | re.DOTALL,
)

_CODE_RE = re.compile(
    r"\[CODE[^\]]*\](?:(?!\[CODE).)*?\[/CODE\]",
    re.IGNORECASE | re.DOTALL,
)
_SIGPIC_RE = re.compile(
    r"\[SIGPIC[^\]]*\](?:(?!\[SIGPIC).)*?\[/SIGPIC\]",
    re.IGNORECASE | re.DOTALL,
)

_TAG_RE = re.compile(r"\[[^\]]+\]")
_MULTI_WS_RE = re.compile(r"\s+")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_BLOCK_BREAK_RE = re.compile(
    r"</?(?:address|article|aside|blockquote|br|dd|div|dl|dt|fieldset|figcaption|"
    r"figure|footer|form|h[1-6]|header|hr|li|main|nav|ol|p|section|table|td|th|tr|ul)\b"
    r"[^>]*>",
    re.IGNORECASE,
)
_PUNCT_TABLE = str.maketrans("", "", string.punctuation)
_NOISE_ATTR_KEYWORDS = (
    "action-bar",
    "actions",
    "advert",
    "archive",
    "archive-box",
    "author-bio",
    "author-box",
    "breadcrumb",
    "breadcrumbs",
    "category-list",
    "comment-list",
    "comments-area",
    "cta",
    "forum-signature",
    "last-edited",
    "login-wall",
    "member-card",
    "member-header",
    "newsletter",
    "notice-banner",
    "post-nav",
    "post-navigation",
    "prev-next",
    "profile-card",
    "promo",
    "quote",
    "reaction-bar",
    "reactions",
    "read-next",
    "recommended",
    "related-articles",
    "related-post",
    "related-posts",
    "reply-actions",
    "share-buttons",
    "sigpic",
    "sign-in",
    "signin",
    "signature",
    "sponsored",
    "sticky-notice",
    "subscribe",
    "table-of-contents",
    "tag-cloud",
    "toc",
    "widget",
    "widget-area",
    "widgets",
    "you-may-also-like",
)
_NOISE_ATTR_PATTERN = "|".join(re.escape(keyword) for keyword in _NOISE_ATTR_KEYWORDS)
_HTML_NOISE_ATTR_BLOCK_RE = re.compile(
    rf"<(?P<tag>[a-z0-9]+)\b"
    rf"(?=[^>]*(?:class|id)\s*=\s*[\"'][^\"']*(?:{_NOISE_ATTR_PATTERN})[^\"']*[\"'])"
    rf"[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_SEMANTIC_NOISE_BLOCK_RE = re.compile(
    r"<(?:aside|footer|form|header|nav)\b[^>]*>.*?</(?:aside|footer|form|header|nav)>",
    re.IGNORECASE | re.DOTALL,
)
_NOISE_LINE_PATTERNS = (
    re.compile(
        r"^(?:related posts?|related articles?|read next|recommended|you may also like)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:table of contents|contents)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:tag cloud|tags?|archives?|categories?|category list)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:previous post|next post|previous|next)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:newsletter|subscribe(?: now)?|sign up)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:share(?: this)?|reply|replies|leave a reply|reactions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:last edited by)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sign in to continue|log in to continue|login to continue)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sponsored|advertisement)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sticky notice|notice)\b",
        re.IGNORECASE,
    ),
)
_INLINE_NOISE_PATTERNS = (
    re.compile(
        r"\bLast edited by\b[^.?!\n]*?(?=(?:[.?!]\s)|(?:\s+[A-Z])|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:sign in to continue|log in to continue|login to continue)\b"
        r"[^.?!\n]*?(?=(?:[.?!]\s)|(?:\s+[A-Z])|$)",
        re.IGNORECASE,
    ),
)
_MAX_NOISE_LINE_LENGTH = 180


def clean_bbcode(raw_text: str) -> str:
    """Strip BBCode from raw text, obliterating QUOTE and CODE block contents.

    Returns plain text with normalized whitespace + NFKC-normalised
    Unicode (pick #13). NFKC folds compatibility-equivalent codepoints
    (`café` precomposed vs decomposed, fullwidth digits, etc.) so all
    downstream signals see a stable byte sequence.
    """
    if not raw_text:
        return ""

    text = raw_text
    text = _obliterate_blocks(text, _QUOTE_RE)
    text = _obliterate_blocks(text, _CODE_RE)
    text = _obliterate_blocks(text, _SIGPIC_RE)
    text = _TAG_RE.sub("", text)
    text = _MULTI_WS_RE.sub(" ", text).strip()
    return _nfkc(text)


def clean_import_text(raw_text: str) -> str:
    """Normalize imported content from either BBCode or rendered WordPress HTML.

    Final step is NFKC normalisation (pick #13) so SHA-256 fingerprints,
    BM25 tokens, and BGE-M3 embeddings all see canonically-equivalent
    text byte-for-byte.
    """
    if not raw_text:
        return ""

    text = _strip_html_noise_blocks(raw_text)
    text = _strip_import_markup_preserving_lines(text)
    text = _HTML_BLOCK_BREAK_RE.sub("\n", text)
    text = unescape(strip_tags(text))
    text = _remove_noise_lines(text)
    text = _strip_inline_noise_phrases(text)
    return _nfkc(_MULTI_WS_RE.sub(" ", text).strip())


def _nfkc(text: str) -> str:
    """NFKC normaliser bound at module import — saves an ``apps.sources.normalize``
    re-import on every call. Pick #13 (Unicode UAX #15)."""
    from apps.sources.normalize import nfkc

    return nfkc(text)


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


def _strip_html_noise_blocks(raw_text: str) -> str:
    """Remove common non-content HTML blocks before tag stripping."""
    text = _HTML_COMMENT_RE.sub("", raw_text)
    text = _obliterate_blocks(text, _SEMANTIC_NOISE_BLOCK_RE)
    text = _obliterate_blocks(text, _HTML_NOISE_ATTR_BLOCK_RE)
    return text


def _strip_import_markup_preserving_lines(raw_text: str) -> str:
    """Strip import markup without flattening line boundaries too early."""
    text = raw_text
    text = _obliterate_blocks(text, _QUOTE_RE)
    text = _obliterate_blocks(text, _CODE_RE)
    text = _obliterate_blocks(text, _SIGPIC_RE)
    return _TAG_RE.sub("", text)


def _remove_noise_lines(text: str) -> str:
    """Drop short boilerplate lines that survive HTML stripping."""
    kept_lines: list[str] = []
    for raw_line in text.splitlines():
        line = _MULTI_WS_RE.sub(" ", raw_line).strip()
        if not line:
            continue
        if _is_noise_line(line):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines)


def _is_noise_line(line: str) -> bool:
    """Return True when a leftover line is likely UI chrome rather than content."""
    if len(line) > _MAX_NOISE_LINE_LENGTH:
        return False
    return any(pattern.search(line) for pattern in _NOISE_LINE_PATTERNS)


def _strip_inline_noise_phrases(text: str) -> str:
    """Remove short boilerplate fragments that can survive as inline text."""
    cleaned = text
    for pattern in _INLINE_NOISE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned
