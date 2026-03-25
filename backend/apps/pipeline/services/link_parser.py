"""Extract internal links from raw content and normalize them into graph edges.

Parses BBCode links, HTML anchors, and bare URLs to find links that point back
to indexed internal content. External links are ignored.

Each edge is a (from_content_id, from_content_type) -> (to_content_id, to_content_type)
relationship, deduplicated per source/destination pair so the earliest
occurrence in the source body becomes the stored representative edge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlparse

_XF_THREAD_RE = re.compile(
    r"/threads/(?:[^/]*\.)?(\d+)(?:/|$)", re.IGNORECASE
)
_XF_RESOURCE_RE = re.compile(
    r"/resources/(?:[^/]*\.)?(\d+)(?:/|$)", re.IGNORECASE
)
_BBCODE_URL_RE = re.compile(
    r"\[URL=([^\]]+)\](.*?)\[/URL\]",
    re.IGNORECASE | re.DOTALL,
)
_HTML_LINK_RE = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_BARE_URL_RE = re.compile(
    r"https?://[^\s\[\]<>\"']+",
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BBCODE_TAG_RE = re.compile(r"\[[^\]]+\]", re.IGNORECASE)
_CONTEXT_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
_CONTEXT_WINDOW_CHARS = 80

EXTRACTION_METHOD_BBCODE = "bbcode_anchor"
EXTRACTION_METHOD_HTML = "html_anchor"
EXTRACTION_METHOD_BARE = "bare_url"

CONTEXT_CLASS_CONTEXTUAL = "contextual"
CONTEXT_CLASS_WEAK = "weak_context"
CONTEXT_CLASS_ISOLATED = "isolated"


@dataclass(frozen=True, slots=True)
class LinkEdge:
    """A single directed edge from one content item to another."""

    from_content_id: int
    from_content_type: str
    to_content_id: int
    to_content_type: str
    anchor_text: str
    extraction_method: str = ""
    link_ordinal: int | None = None
    source_internal_link_count: int | None = None
    context_class: str = ""


@dataclass(frozen=True, slots=True)
class _MatchedLink:
    """A raw link match before URL normalization and target resolution."""

    url: str
    anchor_text: str
    extraction_method: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _ResolvedLink:
    """A resolved internal link before ordinals and source totals are assigned."""

    to_content_id: int
    to_content_type: str
    anchor_text: str
    extraction_method: str
    context_class: str


def extract_internal_links(
    raw_bbcode: str,
    from_content_id: int,
    from_content_type: str,
    forum_domains: list[str] | None = None,
) -> list[LinkEdge]:
    """Parse raw content and return ordered, deduplicated internal link edges."""
    found_links = _find_urls(raw_bbcode)
    if not found_links:
        return []

    seen: set[tuple[int, str]] = set()
    resolved_links: list[_ResolvedLink] = []

    normalized_domains = (
        {d.lower().strip() for d in forum_domains if d.strip()}
        if forum_domains
        else None
    )

    for found_link in found_links:
        normalized_url = normalize_internal_url(found_link.url.strip())
        if not normalized_url:
            continue

        target = _resolve_target(normalized_url, normalized_domains)
        if target is None:
            continue

        to_id, to_type = target

        if to_id == from_content_id and to_type == from_content_type:
            continue

        key = (to_id, to_type)
        if key in seen:
            continue
        seen.add(key)

        resolved_links.append(_ResolvedLink(
            to_content_id=to_id,
            to_content_type=to_type,
            anchor_text=found_link.anchor_text.strip(),
            extraction_method=found_link.extraction_method,
            context_class=_classify_context(raw_bbcode, found_link.start, found_link.end),
        ))

    total_links = len(resolved_links)
    edges: list[LinkEdge] = []
    for ordinal, resolved in enumerate(resolved_links):
        edges.append(LinkEdge(
            from_content_id=from_content_id,
            from_content_type=from_content_type,
            to_content_id=resolved.to_content_id,
            to_content_type=resolved.to_content_type,
            anchor_text=resolved.anchor_text,
            extraction_method=resolved.extraction_method,
            link_ordinal=ordinal,
            source_internal_link_count=total_links,
            context_class=resolved.context_class,
        ))

    return edges


def extract_urls(
    raw_bbcode: str,
    allowed_domains: list[str] | set[str] | None = None,
) -> list[str]:
    """Return deduplicated URLs from BBCode and bare-text links."""
    found_links = _find_urls(raw_bbcode)
    if not found_links:
        return []

    normalized_domains = (
        {d.lower().strip() for d in allowed_domains if d.strip()}
        if allowed_domains
        else None
    )

    urls: list[str] = []
    seen: set[str] = set()

    for found_link in found_links:
        normalized_url = normalize_internal_url(found_link.url.strip())
        if not normalized_url or normalized_url in seen:
            continue
        if normalized_domains is not None:
            try:
                host = (urlparse(normalized_url).hostname or "").lower()
            except Exception:
                continue
            if host not in normalized_domains:
                continue

        seen.add(normalized_url)
        urls.append(normalized_url)

    return urls


def _resolve_target(
    url: str,
    allowed_domains: set[str] | None,
) -> tuple[int, str] | None:
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    if allowed_domains is not None:
        host = (parsed.hostname or "").lower()
        if host not in allowed_domains:
            return None

    path = parsed.path or ""

    match = _XF_THREAD_RE.search(path)
    if match:
        return int(match.group(1)), "thread"

    match = _XF_RESOURCE_RE.search(path)
    if match:
        return int(match.group(1)), "resource"

    try:
        from apps.content.models import ContentItem

        target = (
            ContentItem.objects
            .filter(url=url)
            .values_list("content_id", "content_type")
            .first()
        )
        if target:
            return int(target[0]), str(target[1])
    except Exception:
        return None

    return None


def _find_urls(raw_bbcode: str) -> list[_MatchedLink]:
    if not raw_bbcode:
        return []

    found_links: list[_MatchedLink] = []
    occupied_spans: list[tuple[int, int]] = []

    for match in _BBCODE_URL_RE.finditer(raw_bbcode):
        occupied_spans.append(match.span())
        found_links.append(_MatchedLink(
            url=match.group(1),
            anchor_text=_strip_markup(match.group(2)),
            extraction_method=EXTRACTION_METHOD_BBCODE,
            start=match.start(),
            end=match.end(),
        ))

    for match in _HTML_LINK_RE.finditer(raw_bbcode):
        if _span_overlaps(match.span(), occupied_spans):
            continue
        occupied_spans.append(match.span())
        found_links.append(_MatchedLink(
            url=match.group(1),
            anchor_text=_strip_markup(match.group(2)),
            extraction_method=EXTRACTION_METHOD_HTML,
            start=match.start(),
            end=match.end(),
        ))

    for match in _BARE_URL_RE.finditer(raw_bbcode):
        if _span_overlaps(match.span(), occupied_spans):
            continue
        found_links.append(_MatchedLink(
            url=match.group(0),
            anchor_text="",
            extraction_method=EXTRACTION_METHOD_BARE,
            start=match.start(),
            end=match.end(),
        ))

    found_links.sort(key=lambda link: (link.start, link.end, link.extraction_method))
    return found_links


def normalize_internal_url(url: str) -> str:
    """Canonicalize a live content URL for exact matching across sources."""
    if not url:
        return ""

    try:
        parsed = urlparse(url.strip())
    except Exception:
        return ""

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return ""

    netloc = (parsed.netloc or "").lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    normalized = parsed._replace(scheme=scheme, netloc=netloc, path=path, params="", query="", fragment="")
    return normalized.geturl()


def _strip_markup(value: str) -> str:
    cleaned = unescape(value or "")
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = _BBCODE_TAG_RE.sub("", cleaned)
    return cleaned.strip()


def _span_overlaps(span: tuple[int, int], occupied_spans: list[tuple[int, int]]) -> bool:
    start, end = span
    for other_start, other_end in occupied_spans:
        if start < other_end and end > other_start:
            return True
    return False


def _classify_context(raw_bbcode: str, start: int, end: int) -> str:
    left = _clean_context_window(raw_bbcode[max(0, start - _CONTEXT_WINDOW_CHARS):start])
    right = _clean_context_window(raw_bbcode[end:min(len(raw_bbcode), end + _CONTEXT_WINDOW_CHARS)])
    has_left = _has_context_tokens(left)
    has_right = _has_context_tokens(right)

    if has_left and has_right:
        return CONTEXT_CLASS_CONTEXTUAL
    if has_left or has_right:
        return CONTEXT_CLASS_WEAK
    return CONTEXT_CLASS_ISOLATED


def _clean_context_window(value: str) -> str:
    cleaned = unescape(value or "")
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = _BBCODE_TAG_RE.sub(" ", cleaned)
    cleaned = _BARE_URL_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _has_context_tokens(value: str) -> bool:
    return bool(_CONTEXT_TOKEN_RE.search(value or ""))
