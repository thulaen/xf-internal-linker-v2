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
) -> list[dict[str, Any]]:
    """Fetch URL body chunks for crawling.

    ``headers_by_url`` carries per-URL request headers so callers can
    pipe in conditional-GET validators (``If-None-Match`` /
    ``If-Modified-Since`` from :mod:`apps.sources.conditional_get`).
    The result dict gains ``etag`` and ``last_modified`` keys when the
    server echoes those headers, so callers can persist them onto
    :class:`CrawledPageMeta`.
    """
    sem = asyncio.Semaphore(max_concurrency)
    results: list[dict[str, Any]] = []
    headers_by_url = headers_by_url or {}

    async def fetch(url: str, client: httpx.AsyncClient):
        try:
            # We don't read the whole body if it is too massive, or limit by slicing.
            # Using stream could be better but simplistic approach runs as follows.
            extra_headers = headers_by_url.get(url) or {}
            res = await _bounded_request(
                sem, client, "GET", url, headers=extra_headers
            )
            etag_value = res.headers.get("ETag", "") or res.headers.get("etag", "")
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
        except httpx.TimeoutException:
            results.append(
                {
                    "url": url,
                    "status_code": 0,
                    "content": "",
                    "error": "timeout",
                    "etag": "",
                    "last_modified": "",
                    "encoding": "",
                }
            )
        except httpx.RequestError as exc:
            results.append(
                {
                    "url": url,
                    "status_code": 0,
                    "content": "",
                    "error": str(exc),
                    "etag": "",
                    "last_modified": "",
                    "encoding": "",
                }
            )

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
