"""Trafilatura main-content extraction — pick #7.

Reference
---------
Barbaresi, A. (2021). "Trafilatura: A Web Scraping Library and
Command-Line Tool for Text Discovery and Extraction." *Proceedings
of the 59th Annual Meeting of the ACL: System Demonstrations*,
pp. 122-131.

Goal
----
Strip nav/footer/sidebar/ad chrome from a fetched HTML page and
return the article body plus a small set of metadata fields. Works
better than naive readability heuristics on forum threads + blog
posts because it combines DOM-tree heuristics with text-density
signals.

Wraps the ``trafilatura`` PyPI package. Cold-start safe: when
``trafilatura`` isn't installed, returns ``None`` from
:func:`extract` so callers can branch on the missing-dep path
without crashing.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import trafilatura as _trafilatura

    HAS_TRAFILATURA = True
except ImportError:  # pragma: no cover — depends on pip env
    _trafilatura = None  # type: ignore[assignment]
    HAS_TRAFILATURA = False


@dataclass(frozen=True)
class ExtractedDocument:
    """Trafilatura output — body + the most useful metadata fields."""

    text: str
    title: str | None
    author: str | None
    date: str | None
    source_url: str | None


def is_available() -> bool:
    """True when ``trafilatura`` is importable."""
    return HAS_TRAFILATURA


def extract(
    html: str,
    *,
    url: str | None = None,
    favor_recall: bool = False,
) -> ExtractedDocument | None:
    """Run Trafilatura on *html* and return the extracted document.

    ``url`` is the source URL — Trafilatura uses it to resolve
    relative links and seed metadata. ``favor_recall`` swaps the
    extraction profile from precision (default — fewer false
    positives) to recall (catches more body text on edge cases).

    Returns ``None`` when:

    - The pip dep is missing (cold start).
    - Trafilatura returns no body text (page is all chrome / empty).
    - The HTML is empty / whitespace.

    Real-data ready: install ``trafilatura`` and every call upgrades
    automatically — no caller change required.
    """
    if not html or not html.strip() or not HAS_TRAFILATURA:
        return None
    from apps.core.runtime_flags import is_enabled

    if not is_enabled("trafilatura_extractor.enabled", default=True):
        return None
    # Trafilatura's bare_extraction returns a TrafilaturaDocument /
    # dict-like with keys ['text', 'title', 'author', 'date', ...].
    raw = _trafilatura.bare_extraction(
        html,
        url=url,
        favor_recall=favor_recall,
        include_comments=False,
        include_tables=True,
    )
    if not raw:
        return None
    # bare_extraction returns a TrafilaturaDocument with .as_dict() in
    # newer versions; fall through with getattr defaults for safety.
    if hasattr(raw, "as_dict"):
        d = raw.as_dict()
    elif isinstance(raw, dict):
        d = raw
    else:
        # Older trafilatura returned an object with attributes — read
        # them defensively.
        d = {
            "text": getattr(raw, "text", "") or "",
            "title": getattr(raw, "title", None),
            "author": getattr(raw, "author", None),
            "date": getattr(raw, "date", None),
            "url": getattr(raw, "url", None),
        }
    text = (d.get("text") or "").strip()
    if not text:
        return None
    return ExtractedDocument(
        text=text,
        title=d.get("title") or None,
        author=d.get("author") or None,
        date=d.get("date") or None,
        source_url=d.get("url") or url,
    )
