"""Extract internal links from raw BBCode and normalize into graph edges.

Parses [URL=...]...[/URL] tags and bare URLs to find links that point back
to threads or resources on our own forum.  External links are ignored.

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
        target = _resolve_target(url.strip(), normalized_domains)
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
        normalized_url = url.strip()
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

    return None


def _find_urls(raw_bbcode: str) -> list[tuple[str, str]]:
    if not raw_bbcode:
        return []

    found_links: list[tuple[str, str]] = _BBCODE_URL_RE.findall(raw_bbcode)
    for url in _BARE_URL_RE.findall(raw_bbcode):
        found_links.append((url, ""))
    return found_links
