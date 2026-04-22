"""HTTP conditional-GET helper — ``If-None-Match`` + ``If-Modified-Since``.

Reference: RFC 7232 "Hypertext Transfer Protocol (HTTP/1.1):
Conditional Requests" (Fielding & Reschke, June 2014).

The crawler already stores the previous response's ``ETag`` and
``Last-Modified`` headers on the ``CrawledPage`` row. What it does
NOT do today is send them back on the next fetch — this module is
the small adapter that makes the refetch return ``304 Not Modified``
when the server's content hasn't changed, saving the response body
bandwidth (and the BGE-M3 re-embed cost downstream).

Usage::

    from apps.sources.conditional_get import build_validator_headers, is_not_modified

    cached_etag = crawled_page.etag
    cached_lm = crawled_page.last_modified

    resp = http_client.get(
        url,
        headers={
            **default_headers,
            **build_validator_headers(etag=cached_etag, last_modified=cached_lm),
        },
    )
    if is_not_modified(resp):
        # Body is empty; rely on the cached row.
        mark_page_skipped_304(crawled_page)
    else:
        # Update etag/last_modified with whatever the server sent back.
        crawled_page.etag = resp.headers.get("ETag", "")
        crawled_page.last_modified = resp.headers.get("Last-Modified", "")
        ...

The module is intentionally library-agnostic: it builds and inspects
plain dicts so it works with ``requests``, ``httpx``, ``aiohttp``, or
even the stdlib — the existing pipeline uses multiple clients and
this helper refuses to pick one for them.
"""

from __future__ import annotations

from typing import Any, Mapping


#: HTTP status code 304 — "Not Modified". RFC 7232 §4.1.
STATUS_NOT_MODIFIED: int = 304


def build_validator_headers(
    *,
    etag: str | None,
    last_modified: str | None,
) -> dict[str, str]:
    """Return a headers dict with ``If-None-Match`` / ``If-Modified-Since`` set.

    Passing the previous response's ``ETag`` in ``If-None-Match`` tells
    the origin server "here's what I already have; only send a body if
    your entity tag has changed." ``If-Modified-Since`` is the fallback
    for servers without ETag support, using the previous
    ``Last-Modified`` timestamp.

    Empty / whitespace-only inputs are ignored — passing an empty
    ``If-None-Match`` would match any ETag and is never what the caller
    wants.
    """
    headers: dict[str, str] = {}
    if etag and etag.strip():
        headers["If-None-Match"] = etag.strip()
    if last_modified and last_modified.strip():
        headers["If-Modified-Since"] = last_modified.strip()
    return headers


def is_not_modified(response: Any) -> bool:
    """True when the response is an HTTP 304.

    Accepts any response object that exposes either ``status_code``
    (requests / DRF / httpx) or ``status`` (aiohttp) — saves the
    caller from knowing which client fired the request.
    """
    code = _status_code_of(response)
    return code == STATUS_NOT_MODIFIED


def extract_validators(response: Any) -> dict[str, str]:
    """Return the ETag / Last-Modified pair the *next* request should echo.

    Handles case-insensitive header lookup the way actual HTTP servers
    send headers — ``ETag`` vs ``Etag`` vs ``etag`` all match.
    Returns an empty dict when neither header is present.
    """
    headers = _headers_of(response)
    result: dict[str, str] = {}
    etag = _ci_get(headers, "ETag")
    if etag:
        result["etag"] = etag.strip()
    last_modified = _ci_get(headers, "Last-Modified")
    if last_modified:
        result["last_modified"] = last_modified.strip()
    return result


# ─────────────────────────────────────────────────────────────────────
# Internals — tiny compatibility shims so the helpers above accept
# any HTTP-client response shape without importing the client module.
# ─────────────────────────────────────────────────────────────────────


def _status_code_of(response: Any) -> int:
    for attr in ("status_code", "status"):
        value = getattr(response, attr, None)
        if isinstance(value, int):
            return value
    raise TypeError(
        "conditional_get.is_not_modified: response must expose "
        "`status_code` (requests/httpx/DRF) or `status` (aiohttp)."
    )


def _headers_of(response: Any) -> Mapping[str, str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        raise TypeError(
            "conditional_get.extract_validators: response must expose a "
            "`headers` mapping."
        )
    return headers


def _ci_get(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup, returning the first match or None."""
    # Many HTTP clients give you a CaseInsensitiveDict already; the
    # plain dict fallback covers the stdlib and hand-rolled stubs.
    if hasattr(headers, "get"):
        direct = headers.get(name)
        if direct is not None:
            return direct
    lowered_name = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered_name:
            return value
    return None
