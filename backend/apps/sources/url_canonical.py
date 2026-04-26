"""URL canonicalization per RFC 3986 §6 — pick #08.

Reference
---------
Berners-Lee, T., Fielding, R. & Masinter, L. (January 2005). RFC 3986:
"Uniform Resource Identifier (URI): Generic Syntax." IETF.
<https://datatracker.ietf.org/doc/html/rfc3986>

Goal
----
Collapse the many spellings of a single logical resource onto one
canonical form so the crawler's frontier, the Bloom dedup filter,
and the SHA-256 fingerprint table all key on the same string.
Without this, ``http://Example.com:80/foo/?utm_source=twitter#top`` and
``https://example.com/foo`` (same page) ingest twice.

What we implement (RFC 3986 §6.2.2 + §6.2.3 + project policy):

- Lowercase scheme + host (case-insensitive per §6.2.2.1).
- Strip the default port for the scheme (§6.2.3 — http:80, https:443).
- Normalise dot-segments in the path (§5.2.4).
- Idempotent percent-encoding round-trip on the path (§6.2.2.2).
- Drop the fragment (§3.5 — fragments are client-side).
- Sort query parameters alphabetically (§6.2.2 hint, project policy).
- Strip well-known tracking parameters (UTM, fbclid, gclid, mc_*,
  ref, source) — project-specific dedup concern, not in RFC.

What we deliberately don't do:

- §6.2.4 protocol-based normalisation (e.g. `/index.html` → `/`)
  is site-specific. Operators add per-origin rules elsewhere.
- Lowercasing the path. RFC says path is case-sensitive; folding it
  would create false duplicates on case-sensitive origins (Linux NGINX).

Pure stdlib — no new pip dep. Drop-in replacement for the inline
ad-hoc normaliser in ``site_crawler.py``.
"""

from __future__ import annotations

import logging
from typing import Iterable
from urllib.parse import (
    SplitResult,
    parse_qsl,
    quote,
    unquote,
    urlencode,
    urlsplit,
    urlunsplit,
)

logger = logging.getLogger(__name__)


#: Default tracking-parameter key prefixes stripped from query strings.
#: Sourced from Google Analytics / Facebook Pixel / Mailchimp docs +
#: project empirical observations. Operators can extend per-origin.
DEFAULT_TRACKING_PREFIXES: tuple[str, ...] = (
    "utm_",
    "fbclid",
    "gclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "ref",
    "referrer",
    "source",
    "yclid",
    "igshid",
)


#: Default port per scheme — stripped from the canonical URL.
_DEFAULT_PORTS: dict[str, int] = {
    "http": 80,
    "https": 443,
    "ftp": 21,
    "ws": 80,
    "wss": 443,
}


def canonicalize(
    url: str,
    *,
    drop_fragment: bool = True,
    strip_tracking_params: bool = True,
    sort_query_params: bool = True,
    tracking_prefixes: Iterable[str] = DEFAULT_TRACKING_PREFIXES,
) -> str:
    """Return the canonical form of *url* per RFC 3986 §6.

    Raises
    ------
    ValueError
        On a relative URL or one whose scheme/host stdlib refuses to
        parse. Caller must resolve relative URLs against a base URL
        first (the crawler's sitemap step does this).
    """
    if not url:
        raise ValueError("URL must be non-empty")

    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"URL must be absolute (scheme + host required): {url!r}")

    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError(f"URL has no host: {url!r}")

    # Default-port stripping (§6.2.3).
    port = parts.port
    if port is not None and _DEFAULT_PORTS.get(scheme) == port:
        port = None

    # Normalise dot-segments + percent-encoding (§5.2.4 + §6.2.2.2).
    path = _normalise_path(parts.path) or "/"

    # Query handling (§6.2.2 + project policy).
    qs_pairs = parse_qsl(parts.query, keep_blank_values=True)
    if strip_tracking_params:
        prefixes = tuple(tracking_prefixes)
        qs_pairs = [
            (k, v) for (k, v) in qs_pairs if not _matches_tracking_prefix(k, prefixes)
        ]
    if sort_query_params:
        qs_pairs.sort()
    query = urlencode(qs_pairs, doseq=True)

    fragment = "" if drop_fragment else parts.fragment

    # Reassemble with userinfo + host + optional port.
    userinfo = parts.username or ""
    if parts.password:
        userinfo += f":{parts.password}"
    authority = host + (f":{port}" if port else "")
    if userinfo:
        authority = f"{userinfo}@{authority}"

    return urlunsplit(SplitResult(scheme, authority, path, query, fragment))


def is_canonical(url: str) -> bool:
    """True iff ``url == canonicalize(url)`` — useful for the import dedup audit.

    Defaults match :func:`canonicalize`. Failures of canonicalisation
    (e.g. relative URL) return ``False`` instead of raising — callers
    auditing existing rows shouldn't crash on a single bad value.
    """
    try:
        return url == canonicalize(url)
    except ValueError:
        return False


# ── Internals ──────────────────────────────────────────────────────


def _matches_tracking_prefix(key: str, prefixes: tuple[str, ...]) -> bool:
    """True iff *key* starts with any of *prefixes* (case-insensitive)."""
    lowered = key.lower()
    return any(lowered.startswith(p) for p in prefixes)


def _normalise_path(path: str) -> str:
    """RFC 3986 §5.2.4 'Remove Dot Segments' + percent-encoding round-trip.

    Stdlib has no direct helper — the loop below is the published
    algorithm verbatim. Idempotent.
    """
    # Round-trip percent encoding so all characters are encoded
    # consistently (single-canonical-form-per-byte invariant).
    raw = quote(unquote(path), safe="/:@%+,;=~!$&'()*")

    # §5.2.4 Remove Dot Segments.
    output: list[str] = []
    input_buf = raw
    while input_buf:
        if input_buf.startswith("../"):
            input_buf = input_buf[3:]
        elif input_buf.startswith("./"):
            input_buf = input_buf[2:]
        elif input_buf.startswith("/./"):
            input_buf = "/" + input_buf[3:]
        elif input_buf == "/.":
            input_buf = "/"
        elif input_buf.startswith("/../"):
            input_buf = "/" + input_buf[4:]
            if output:
                output.pop()
        elif input_buf == "/..":
            input_buf = "/"
            if output:
                output.pop()
        elif input_buf in (".", ".."):
            input_buf = ""
        else:
            # Move first segment (everything up to the next "/" after
            # the leading char) from input to output.
            if input_buf.startswith("/"):
                slash = input_buf.find("/", 1)
            else:
                slash = input_buf.find("/")
            if slash == -1:
                output.append(input_buf)
                input_buf = ""
            else:
                output.append(input_buf[:slash])
                input_buf = input_buf[slash:]

    # Collapse repeated slashes that the algorithm above can't see —
    # they're a project-policy concern, not §5.2.4 (the RFC treats
    # them as significant). Empirically every origin we crawl treats
    # `//` as `/`.
    result = "".join(output)
    while "//" in result:
        result = result.replace("//", "/")
    return result
