"""Extract internal links from raw content and normalize into graph edges.

Parses BBCode links, HTML anchors, and bare URLs to find links that point back
to indexed internal content. External links are ignored.

Each edge is a (from_content_id, from_content_type) -> (to_content_id, to_content_type)
relationship, deduplicated per source post.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class LinkEdge:
    """A single directed edge from one content item to another."""

    from_content_id: int
    from_content_type: str
    to_content_id: int
    to_content_type: str
    anchor_text: str


def extract_internal_links(
    raw_bbcode: str,
    from_content_id: int,
    from_content_type: str,
    forum_domains: list[str] | None = None,
) -> list[LinkEdge]:
    """Parse raw BBCode and return deduplicated internal link edges."""
    found_links = _find_urls(raw_bbcode)
    if not found_links:
        return []

    seen: set[tuple[int, str]] = set()
    edges: list[LinkEdge] = []

    normalized_domains = (
        {d.lower().strip() for d in forum_domains if d.strip()}
        if forum_domains
        else None
    )

    for url, anchor in found_links:
        normalized_url = normalize_internal_url(url.strip())
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

        edges.append(LinkEdge(
            from_content_id=from_content_id,
            from_content_type=from_content_type,
            to_content_id=to_id,
            to_content_type=to_type,
            anchor_text=anchor.strip(),
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

    for url, _anchor in found_links:
        normalized_url = normalize_internal_url(url.strip())
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


def _find_urls(raw_bbcode: str) -> list[tuple[str, str]]:
    if not raw_bbcode:
        return []

    found_links: list[tuple[str, str]] = _BBCODE_URL_RE.findall(raw_bbcode)
    found_links.extend(
        (url, _strip_markup(anchor))
        for url, anchor in _HTML_LINK_RE.findall(raw_bbcode)
    )
    for url in _BARE_URL_RE.findall(raw_bbcode):
        found_links.append((url, ""))
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
    return re.sub(r"<[^>]+>", "", value or "").strip()
