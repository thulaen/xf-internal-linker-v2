from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET  # nosec B405
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]  # Docker-only dependency


def run_async(coro):
    """Thin asyncio.run wrapper for Celery contexts."""
    return asyncio.run(coro)


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
    except Exception:
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
        except Exception:
            status_code = 0
            redirect_url = ""

        # Tuple structure matches what scan_via_http_worker previously returned.
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
        tasks = [asyncio.create_task(fetch(url, client)) for url in urls]
        await asyncio.gather(*tasks)

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

    ``headers_by_url`` carries per-URL request headers so callers can
    pipe in conditional-GET validators (``If-None-Match`` /
    ``If-Modified-Since`` from :mod:`apps.sources.conditional_get`).
    The result dict gains ``etag`` and ``last_modified`` keys when the
    server echoes those headers, so callers can persist them onto
    :class:`CrawledPageMeta`.

    ``rate_limiter_key`` (pick #1 — Turner 1986 token bucket) gates each
    outbound request on a token from the named bucket in
    :data:`apps.sources.token_bucket.DEFAULT_REGISTRY`. Callers register
    the bucket up-front (typically per origin host) with the desired
    ``tokens_per_second`` / ``burst_capacity``; if no key is passed the
    limiter is skipped and only the concurrency semaphore applies.

    ``rate_limiter_timeout`` caps how long a single request waits for a
    token before recording a ``rate_limited`` error and moving on.

    ``max_attempts`` (pick #2 — Metcalfe & Boggs 1976 / AWS full-jitter
    backoff) sets the total request attempts per URL. ``1`` (default)
    disables retry, preserving prior single-shot behaviour. Values > 1
    enable AWS full-jitter retry on transient HTTP errors only
    (``httpx.TimeoutException``, ``httpx.RequestError`` — i.e. network
    + timeout). Application-level 4xx/5xx are NOT retried by this
    layer — that's the caller's policy decision (a 404 doesn't become
    a 200 by retrying).

    ``backoff_base`` and ``backoff_cap`` define the jitter window per
    :func:`apps.sources.backoff.full_jitter_delay`: each retry sleeps a
    random duration in ``[0, min(cap, base * 2 ** attempt)]``.

    ``circuit_breaker`` (pick #3 — Nygard 2007 *Release It!*) is an
    optional :class:`apps.pipeline.services.circuit_breaker.CircuitBreaker`
    instance. When supplied, every request first checks
    ``breaker.is_open()``; if OPEN, the request is fast-failed with
    ``error="circuit_open"`` and no HTTP call is made. Successful
    fetches call ``breaker.record_success()``; transient failures (the
    same ``httpx.TimeoutException`` / ``RequestError`` that the
    backoff loop retries) call ``breaker.record_failure()``. The
    breaker's state machine then drives CLOSED → OPEN → HALF_OPEN →
    CLOSED transitions per its configured thresholds.
    """
    sem = asyncio.Semaphore(max_concurrency)
    results: list[dict[str, Any]] = []
    headers_by_url = headers_by_url or {}

    if rate_limiter_key is not None:
        # Local import keeps async_http importable in minimal test
        # contexts that don't load the source layer.
        from apps.sources.token_bucket import DEFAULT_REGISTRY as _RATE_LIMITER
    else:
        _RATE_LIMITER = None

    if max_attempts > 1:
        from apps.sources.backoff import full_jitter_delay as _full_jitter_delay
    else:
        _full_jitter_delay = None

    async def fetch(url: str, client: httpx.AsyncClient):
        # Pick #1 — wait for a token before issuing the HTTP request.
        # The bucket's wait is sync (uses time.sleep) and thread-safe;
        # offload to a worker thread so the asyncio event loop stays
        # responsive for the other in-flight requests.
        if _RATE_LIMITER is not None and rate_limiter_key is not None:
            acquired = await asyncio.to_thread(
                _RATE_LIMITER.wait_and_acquire,
                rate_limiter_key,
                cost=1.0,
                timeout=rate_limiter_timeout,
            )
            if not acquired:
                results.append(
                    {
                        "url": url,
                        "status_code": 0,
                        "content": "",
                        "error": "rate_limited",
                        "etag": "",
                        "last_modified": "",
                        "encoding": "",
                    }
                )
                return

        # Pick #3 — Nygard circuit breaker. Fast-fail when the per-host
        # breaker is OPEN so a downed origin doesn't drain the
        # concurrency pool with timeouts. ``is_open`` advances
        # HALF_OPEN transitions for us, so a long-quiet OPEN flips
        # automatically when the recovery window expires.
        if circuit_breaker is not None and circuit_breaker.is_open():
            results.append(
                {
                    "url": url,
                    "status_code": 0,
                    "content": "",
                    "error": "circuit_open",
                    "etag": "",
                    "last_modified": "",
                    "encoding": "",
                }
            )
            return

        # Pick #2 — AWS full-jitter retry loop. ``max_attempts == 1``
        # makes the loop a single iteration with no sleep, which is
        # the pre-pick-2 behaviour. ``last_error`` carries the row we
        # would record if every attempt fails.
        last_error: dict[str, Any] | None = None
        for attempt in range(max_attempts):
            try:
                extra_headers = headers_by_url.get(url) or {}
                res = await _bounded_request(
                    sem, client, "GET", url, headers=extra_headers
                )
                etag_value = res.headers.get("ETag", "") or res.headers.get(
                    "etag", ""
                )
                lm_value = res.headers.get("Last-Modified", "") or res.headers.get(
                    "last-modified", ""
                )
                # 304 responses have empty bodies — that's correct,
                # the caller treats `status_code=304` as "unchanged".
                if res.status_code == 304:
                    body = ""
                    encoding_used = ""
                else:
                    # Pick #11 — explicit encoding detection beats httpx's
                    # heuristic on origins that don't declare charset.
                    body, encoding_used = _decode_response_body(
                        res, max_body_bytes=max_body_bytes
                    )
                results.append(
                    {
                        "url": url,
                        "status_code": res.status_code,
                        "content": body,
                        "error": None,
                        "etag": etag_value,
                        "last_modified": lm_value,
                        "encoding": encoding_used,
                    }
                )
                # Successful response — tell the breaker (if any) that
                # the origin is healthy. Drives HALF_OPEN → CLOSED.
                if circuit_breaker is not None:
                    circuit_breaker.record_success()
                return
            except httpx.TimeoutException:
                last_error = {
                    "url": url,
                    "status_code": 0,
                    "content": "",
                    "error": "timeout",
                    "etag": "",
                    "last_modified": "",
                    "encoding": "",
                }
                if circuit_breaker is not None:
                    circuit_breaker.record_failure()
            except httpx.RequestError as exc:
                last_error = {
                    "url": url,
                    "status_code": 0,
                    "content": "",
                    "error": str(exc),
                    "etag": "",
                    "last_modified": "",
                    "encoding": "",
                }
                if circuit_breaker is not None:
                    circuit_breaker.record_failure()
            # Sleep before next attempt (skipped on the final iteration
            # because ``return`` after results.append below ends the
            # coroutine — no point sleeping for nothing).
            if _full_jitter_delay is not None and attempt < max_attempts - 1:
                delay = _full_jitter_delay(
                    attempt, base=backoff_base, cap=backoff_cap
                )
                await asyncio.sleep(delay)
        # Loop exhausted — record the last failure.
        if last_error is not None:
            results.append(last_error)

    async with httpx.AsyncClient(
        http2=True, follow_redirects=True, timeout=timeout
    ) as client:
        tasks = [asyncio.create_task(fetch(url, client)) for url in urls]
        await asyncio.gather(*tasks)

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
        except Exception as exc:
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
    except Exception as exc:
        return [], f"Parse error: {exc}"

    return urls, None
