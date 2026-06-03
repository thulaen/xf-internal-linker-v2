"""Async http module for the pipeline app."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET  # nosec B405
from typing import Any, NamedTuple

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]  # Docker-only dependency


def run_async(coro):
    """Thin asyncio.run wrapper for Celery contexts."""
    return asyncio.run(coro)


def _make_fetch_record(
    url: str,
    *,
    status_code: int = 0,
    content: str = "",
    error: str | None = None,
    etag: str = "",
    last_modified: str = "",
    encoding: str = "",
) -> dict[str, Any]:
    """Single factory for the per-URL result dict returned from :func:`fetch_urls`.

    Centralising the seven-key record shape eliminates the 6× inline
    dict-literal boilerplate the function used to carry and ensures
    every code path returns the same field set (downstream code
    indexes by name, so a missing key would silently break callers).
    """
    return {
        "url": url,
        "status_code": status_code,
        "content": content,
        "error": error,
        "etag": etag,
        "last_modified": last_modified,
        "encoding": encoding,
    }


def _extract_response_validators(res: "httpx.Response") -> tuple[str, str]:
    """Read ETag + Last-Modified from a response, accepting either capitalisation.

    Some origins respond with ``ETag`` / ``Last-Modified`` and others
    with the lower-case form; the conditional-GET write path expects
    both to be normalised to a single value per validator.
    """
    etag = res.headers.get("ETag", "") or res.headers.get("etag", "")
    last_modified = res.headers.get("Last-Modified", "") or res.headers.get(
        "last-modified", ""
    )
    return etag, last_modified


class _FetchConfig(NamedTuple):
    """Bundle of per-call knobs threaded into :func:`_fetch_one`.

    Bundled so :func:`_fetch_one` stays under the linter's 7-arg cap and
    so :func:`fetch_urls` can hand every URL the same config object
    without repeating the long argument list.
    """

    sem: asyncio.Semaphore
    max_body_bytes: int
    max_attempts: int
    backoff_base: float
    backoff_cap: float
    rate_limiter: object | None
    rate_limiter_key: str | None
    rate_limiter_timeout: float
    circuit_breaker: object | None
    full_jitter_delay: object | None
    headers_by_url: dict[str, dict[str, str]]


async def _wait_for_rate_limit_token(config: _FetchConfig) -> bool:
    """Return True iff a token was acquired (or no limiter is configured)."""
    if config.rate_limiter is None or config.rate_limiter_key is None:
        return True
    return await asyncio.to_thread(
        config.rate_limiter.wait_and_acquire,
        config.rate_limiter_key,
        cost=1.0,
        timeout=config.rate_limiter_timeout,
    )


async def _attempt_one_request(
    url: str,
    client: "httpx.AsyncClient",
    config: _FetchConfig,
) -> dict[str, Any]:
    """Make one GET attempt. Returns a populated record on success, raises on failure."""
    extra_headers = config.headers_by_url.get(url) or {}
    res = await _bounded_request(config.sem, client, "GET", url, headers=extra_headers)
    etag_value, lm_value = _extract_response_validators(res)
    # 304 responses have empty bodies — the caller treats `status_code=304`
    # as "unchanged" and skips body decoding.
    if res.status_code == 304:
        body, encoding_used = "", ""
    else:
        # Pick #11 — explicit encoding detection beats httpx's heuristic
        # on origins that don't declare charset.
        body, encoding_used = _decode_response_body(
            res, max_body_bytes=config.max_body_bytes
        )
    return _make_fetch_record(
        url,
        status_code=res.status_code,
        content=body,
        etag=etag_value,
        last_modified=lm_value,
        encoding=encoding_used,
    )


async def _fetch_one(
    url: str,
    client: "httpx.AsyncClient",
    results: list[dict[str, Any]],
    config: _FetchConfig,
) -> None:
    """Fetch one URL, applying rate-limit, circuit-breaker, and retry policies.

    Appends exactly one record dict to ``results`` (success or failure).
    Never raises — every failure path is recorded as a row.
    """
    # Pick #1 — wait for a rate-limit token before issuing the HTTP request.
    if not await _wait_for_rate_limit_token(config):
        results.append(_make_fetch_record(url, error="rate_limited"))
        return

    # Pick #3 — Nygard circuit breaker. Fast-fail when OPEN so a downed
    # origin doesn't drain the concurrency pool with timeouts.
    breaker = config.circuit_breaker
    if breaker is not None and breaker.is_open():
        results.append(_make_fetch_record(url, error="circuit_open"))
        return

    # Pick #2 — AWS full-jitter retry loop. ``max_attempts == 1`` makes the
    # loop a single iteration with no sleep (the pre-pick-2 behaviour).
    last_error: dict[str, Any] | None = None
    for attempt in range(config.max_attempts):
        try:
            record = await _attempt_one_request(url, client, config)
            results.append(record)
            if breaker is not None:
                breaker.record_success()
            return
        except httpx.TimeoutException:
            last_error = _make_fetch_record(url, error="timeout")
            if breaker is not None:
                breaker.record_failure()
        except httpx.RequestError as exc:
            last_error = _make_fetch_record(url, error=str(exc))
            if breaker is not None:
                breaker.record_failure()
        # Sleep before next attempt; skip on the final iteration since the
        # next move is to record last_error and return.
        if config.full_jitter_delay is not None and attempt < config.max_attempts - 1:
            delay = config.full_jitter_delay(
                attempt, base=config.backoff_base, cap=config.backoff_cap
            )
            await asyncio.sleep(delay)
    if last_error is not None:
        results.append(last_error)


async def _bounded_request(
    sem: asyncio.Semaphore, client: httpx.AsyncClient, method: str, url: str, **kw
) -> httpx.Response:
    """Execute an HTTP request bounded by a semaphore for concurrency limits."""
    async with sem:
        return await client.request(method, url, **kw)


def _decode_response_body(
    res: "httpx.Response", *, max_body_bytes: int
) -> tuple[str, str]:
    """Decode an httpx response body via pick #11's encoding-detect helper.

    Returns a ``(text, encoding)`` pair. ``encoding`` is the codec
    name actually used so callers can persist it for diagnostics.
    Falls back to httpx's built-in ``res.text`` when the helper isn't
    available — the import is local so async_http stays usable in
    minimal test contexts that don't load the full source layer.
    """
    raw_bytes = res.content[:max_body_bytes]
    if not raw_bytes:
        return "", ""
    try:
        from apps.sources.encoding import decode_with_guess, detect_encoding
    except Exception:  # noqa: BLE001  # Source layer isn't importable in minimal test contexts — fall back to httpx's built-in encoding heuristic.
        # Source layer isn't importable — fall back to httpx heuristic.
        return res.text[:max_body_bytes], ""
    guess = detect_encoding(
        raw_bytes,
        content_type_header=res.headers.get("Content-Type"),
    )
    text = decode_with_guess(raw_bytes, guess)
    return text, guess.encoding


async def probe_urls(
    urls: list[str],
    *,
    max_concurrency: int = 50,
    timeout: float = 10.0,
    user_agent: str = "XF Internal Linker V2 Broken Link Scanner",
    on_progress=None,
) -> dict[str, tuple[int, str]]:
    """Probe URLs for health status and redirects using async HTTP.

    Absorbs legacy fallback logic:
    - Bounded concurrency via Semaphore
    - HEAD first -> GET fallback on 405/501
    - Timeout extraction returns (0, "")
    - Extracts redirect URL from the Location header
    """
    sem = asyncio.Semaphore(max_concurrency)
    results: dict[str, tuple[int, str]] = {}
    completed = 0
    transport = httpx.AsyncHTTPTransport(retries=0)

    async def fetch(url: str, client: httpx.AsyncClient):
        nonlocal completed
        try:
            res = await _bounded_request(sem, client, "HEAD", url)
            if res.status_code in (405, 501):
                res = await _bounded_request(sem, client, "GET", url)
            status_code = res.status_code
            redirect_url = res.headers.get("Location", "")
            # Ensure absolute redirect
            if redirect_url and redirect_url.startswith("/"):
                base = str(res.url) if res.url else url
                from urllib.parse import urljoin

                redirect_url = urljoin(base, redirect_url)
        except httpx.TimeoutException:
            status_code = 0
            redirect_url = ""
        except httpx.RequestError:
            status_code = 0
            redirect_url = ""
        except Exception:  # noqa: BLE001  # Per-URL probe in a bulk fetch — record the URL as "unreachable" (status_code=0) rather than abort the whole batch on a single weird failure.
            status_code = 0
            redirect_url = ""

        result = (status_code, redirect_url)
        results[url] = result

        completed += 1
        if on_progress:
            on_progress(completed, url, result)

    async with httpx.AsyncClient(
        http2=True,
        transport=transport,
        timeout=timeout,
        headers={"User-Agent": user_agent},
        follow_redirects=False,
    ) as client:
        await asyncio.gather(*(fetch(url, client) for url in urls))

    return results


async def fetch_urls(
    urls: list[str],
    *,
    max_concurrency: int = 25,
    max_body_bytes: int = 5_242_880,
    timeout: float = 30.0,
    headers_by_url: dict[str, dict[str, str]] | None = None,
    rate_limiter_key: str | None = None,
    rate_limiter_timeout: float = 60.0,
    max_attempts: int = 1,
    backoff_base: float = 1.0,
    backoff_cap: float = 30.0,
    circuit_breaker: object | None = None,
) -> list[dict[str, Any]]:
    """Fetch URL body chunks for crawling.

    Returns a list of records (one per URL) with the seven keys defined
    by :func:`_make_fetch_record`. Per-URL fetch logic — rate-limit,
    circuit-breaker, retry — lives in :func:`_fetch_one`; this
    orchestrator just builds the :class:`_FetchConfig` and dispatches.

    Pick references (see :mod:`apps.sources.token_bucket`,
    :mod:`apps.sources.backoff`, and
    :mod:`apps.pipeline.services.circuit_breaker` for full citations):

    - ``headers_by_url`` — per-URL conditional-GET validators
      (``If-None-Match`` / ``If-Modified-Since``).
    - ``rate_limiter_key`` (pick #1 — Turner 1986 token bucket) names
      a bucket in ``DEFAULT_REGISTRY``; ``rate_limiter_timeout`` caps
      the per-request token wait.
    - ``max_attempts`` / ``backoff_base`` / ``backoff_cap`` (pick #2 —
      AWS full-jitter retry) — only retries network/timeout errors,
      not 4xx/5xx.
    - ``circuit_breaker`` (pick #3 — Nygard 2007 *Release It!*) —
      optional per-host breaker; OPEN state fast-fails with
      ``error="circuit_open"``.
    """
    results: list[dict[str, Any]] = []
    if rate_limiter_key is not None:
        # Local import keeps async_http importable in minimal test
        # contexts that don't load the source layer.
        from apps.sources.token_bucket import DEFAULT_REGISTRY as _rate_limiter
    else:
        _rate_limiter = None
    if max_attempts > 1:
        from apps.sources.backoff import full_jitter_delay as _full_jitter_delay
    else:
        _full_jitter_delay = None

    config = _FetchConfig(
        sem=asyncio.Semaphore(max_concurrency),
        max_body_bytes=max_body_bytes,
        max_attempts=max_attempts,
        backoff_base=backoff_base,
        backoff_cap=backoff_cap,
        rate_limiter=_rate_limiter,
        rate_limiter_key=rate_limiter_key,
        rate_limiter_timeout=rate_limiter_timeout,
        circuit_breaker=circuit_breaker,
        full_jitter_delay=_full_jitter_delay,
        headers_by_url=headers_by_url or {},
    )

    async with httpx.AsyncClient(
        http2=True, follow_redirects=True, timeout=timeout
    ) as client:
        await asyncio.gather(*(_fetch_one(url, client, results, config) for url in urls))
    return results

    return results


async def crawl_sitemap(
    sitemap_url: str, *, max_urls: int = 10_000, timeout: float = 30.0
) -> tuple[list[str], str | None]:
    """Download and extract URLs from an XML sitemap."""
    async with httpx.AsyncClient(
        http2=True, timeout=timeout, follow_redirects=True
    ) as client:
        try:
            res = await client.get(sitemap_url)
            res.raise_for_status()
        except Exception as exc:  # noqa: BLE001  # Sitemap fetch can fail many ways (DNS, 4xx/5xx, connect timeout); return the failure message so the caller's UI surfaces it to the operator.
            return [], str(exc)

    urls = []
    try:
        # Simplistic XML parsing for sitemaps.
        # Namespaces are usually present.
        root = ET.fromstring(res.text)  # nosec B314
        namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls_elements = root.findall(".//ns:url/ns:loc", namespace)
        if not urls_elements:
            # Fallback without namespace
            urls_elements = root.findall(".//url/loc")

        for el in urls_elements[:max_urls]:
            if el.text:
                urls.append(el.text.strip())
    except Exception as exc:  # noqa: BLE001  # XML parse failure on operator-supplied sitemap URL — return the parse error so the operator can fix the sitemap or pick a different one.
        return [], f"Parse error: {exc}"

    return urls, None
