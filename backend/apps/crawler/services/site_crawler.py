import asyncio
import json
import logging
from datetime import timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from django.utils import timezone

from apps.crawler.models import CrawledPageMeta, CrawlSession, SitemapConfig
from apps.pipeline.services.async_http import crawl_sitemap, fetch_urls
from apps.sources.conditional_get import build_validator_headers
from apps.sources.freshness_frontier import compute_skip_set as freshness_skip_set
from apps.sources.hyperloglog_registry import REGISTRY as HLL_REGISTRY
from apps.sources.robots import RobotsChecker
from apps.sources.sha256_fingerprint import fingerprint as content_fingerprint
from apps.sources.url_canonical import canonicalize as canonicalize_url

logger = logging.getLogger(__name__)

#: One per-process robots checker — its 24-h TTL cache amortises per-origin
#: robots.txt fetches across crawl sessions. RFC 9309 §3 default TTL.
_ROBOTS_CHECKER = RobotsChecker()


def run_crawl_session_sync(session_id) -> None:
    """Entry point for Celery to run the crawler logic synchronously."""
    try:
        asyncio.run(_execute_crawl_session(session_id))
    except Exception as exc:
        logger.exception("Crawl session failed: %s", exc)
        try:
            session = CrawlSession.objects.get(pk=session_id)
            session.status = "failed"
            session.error_message = str(exc)
            session.save(update_fields=["status", "error_message", "updated_at"])
        except CrawlSession.DoesNotExist:
            logger.debug("CrawlSession %s not found during error update", session_id)


async def _execute_crawl_session(session_id) -> None:
    session = await CrawlSession.objects.select_related().aget(pk=session_id)
    if session.status not in ("pending", "paused"):
        logger.warning(f"Session {session_id} is in status {session.status}, skipping.")
        return

    session.status = "running"
    if not session.started_at:
        session.started_at = timezone.now()
    session.message = "Initializing frontier..."
    await session.asave(update_fields=["status", "started_at", "message"])

    domain = session.site_domain
    base_url = f"https://{domain}"

    # Generate Frontier from Sitemaps or Root
    frontier_urls = set()
    async for sitemap in SitemapConfig.objects.filter(domain=domain, is_enabled=True):
        urls, _ = await crawl_sitemap(sitemap.sitemap_url)
        frontier_urls.update(urls)

    if not frontier_urls:
        frontier_urls.add(base_url)

    # Filtering logic (excluded_paths)
    excluded_paths = session.config.get("excluded_paths", [])
    valid_urls = []
    for u in frontier_urls:
        parsed = urlparse(u)
        if hasattr(parsed, "netloc") and parsed.netloc != domain:
            continue
        if any(parsed.path.startswith(ep) for ep in excluded_paths):
            continue
        valid_urls.append(u)

    # Exclude already crawled in this session
    already_crawled = set(
        await asyncio.to_thread(
            lambda: list(
                CrawledPageMeta.objects.filter(session=session).values_list(
                    "url", flat=True
                )
            )
        )
    )

    to_crawl = list(set(valid_urls) - already_crawled)

    # Pick #09 — drop URLs that robots.txt forbids before we waste a fetch.
    # The RobotsChecker fails open per RFC 9309 §3.1 if robots.txt is
    # unreachable, so this only filters out genuine Disallows.
    if to_crawl:
        allowed: list[str] = []
        blocked = 0
        for u in to_crawl:
            try:
                if _ROBOTS_CHECKER.is_allowed(u):
                    allowed.append(u)
                else:
                    blocked += 1
            except Exception:
                # Robots fetch hiccup — fail open, queue the URL.
                allowed.append(u)
        if blocked:
            logger.info(
                "robots.txt: filtered %d / %d URLs in session %s",
                blocked,
                len(to_crawl),
                session_id,
            )
        to_crawl = allowed

    # Pick #10 — Cho-Garcia-Molina freshness gate. Drop URLs whose
    # last successful crawl is more recent than their adaptive
    # refresh interval. URLs without history pass through unchanged
    # (every new URL gets crawled at least once). Uses one bulk
    # query against CrawledPageMeta — no N+1.
    if to_crawl:
        try:
            skipped = await asyncio.to_thread(freshness_skip_set, to_crawl)
        except Exception:
            logger.debug("freshness_skip_set failed; not filtering", exc_info=True)
            skipped = set()
        if skipped:
            logger.info(
                "freshness gate: skipping %d / %d URLs in session %s "
                "(crawled too recently)",
                len(skipped),
                len(to_crawl),
                session_id,
            )
            to_crawl = [u for u in to_crawl if u not in skipped]

    # Pick #06 — preload cached ETag / Last-Modified per URL so the
    # next chunk's fetch_urls call sends If-None-Match / If-Modified-Since.
    cached_validators: dict[str, dict[str, str]] = {}
    if to_crawl:
        prior_validators = await asyncio.to_thread(
            lambda: list(
                CrawledPageMeta.objects.filter(
                    url__in=to_crawl,
                )
                .exclude(etag="", last_modified="")
                .values("url", "etag", "last_modified")
            )
        )
        for row in prior_validators:
            headers = build_validator_headers(
                etag=row.get("etag"),
                last_modified=row.get("last_modified"),
            )
            if headers:
                cached_validators[row["url"]] = headers

    rate_limit = session.config.get("rate_limit", 4)
    timeout_hours = session.config.get("timeout_hours", 2)
    end_time = timezone.now() + timedelta(hours=timeout_hours)

    session.message = f"Crawling {len(to_crawl)} URLs at {rate_limit} req/s..."
    await session.asave(update_fields=["message"])

    # Strict chunk limit of 10 to protect memory per user request
    chunk_size = min(rate_limit, 10)

    for i in range(0, len(to_crawl), chunk_size):
        if timezone.now() > end_time:
            session.status = "paused"
            session.message = "Timeout reached. Pausing."
            session.is_resumable = True
            await session.asave()
            return

        # Refetch session in case user paused it
        await session.arefresh_from_db(fields=["status"])
        if session.status != "running":
            return

        chunk = to_crawl[i : i + chunk_size]
        chunk_validators = {
            u: cached_validators[u] for u in chunk if u in cached_validators
        }
        responses = await fetch_urls(
            chunk,
            max_concurrency=rate_limit,
            headers_by_url=chunk_validators,
        )

        for res in responses:
            raw_url = res["url"]
            status_code = res["status_code"]
            body = res["content"]
            new_etag = res.get("etag", "")
            new_last_modified = res.get("last_modified", "")

            # Pick #08 — RFC 3986 §6 canonicalisation. Replaces the
            # earlier inline normaliser (lower-host + drop-fragment) with
            # the full RFC contract: case-folding, default-port stripping,
            # dot-segment resolution, percent-encoding round-trip,
            # tracking-param scrub, query sort.
            try:
                normalized_url = canonicalize_url(raw_url)
            except ValueError:
                # Origin returned a malformed URL — keep the raw form so
                # the row still saves and operators can investigate.
                logger.debug("URL canonicalisation failed for %s", raw_url)
                normalized_url = raw_url

            # Pick #05 — record the canonical URL in the cardinality
            # counter so the dashboard can answer "how many unique
            # pages have we ever crawled?" in O(1).
            try:
                HLL_REGISTRY.add("crawl_unique_urls", normalized_url)
            except Exception:
                logger.debug("HLL counter update failed for %s", normalized_url)

            meta = CrawledPageMeta(
                session=session,
                url=raw_url,
                normalized_url=normalized_url,
                http_status=status_code,
                content_length=len(body) if body else 0,
                etag=new_etag[:200],
                last_modified=new_last_modified[:200],
            )

            # Pick #06 — RFC 7232 §4.1: 304 means "your cached copy is
            # current". Skip parse + content_length tracking; the caller
            # relies on the prior CrawledPageMeta row for the body.
            if status_code == 304:
                meta.content_length = 0
                logger.debug(
                    "conditional GET 304: %s (cache hit, body skipped)", raw_url
                )
            elif status_code == 200 and body:
                try:
                    await asyncio.to_thread(_parse_html, body, meta, raw_url)
                except Exception as ex:
                    logger.warning("Failed to parse %s: %s", raw_url, ex)
            elif status_code >= 400:
                meta.consecutive_404_count = 1
                session.broken_links_found += 1

            await asyncio.to_thread(_save_page_meta, meta)

            session.pages_crawled += 1
            session.bytes_downloaded += len(body) if body else 0
            session.progress = (
                session.pages_crawled / len(valid_urls) if valid_urls else 1.0
            )

        await session.asave(
            update_fields=[
                "pages_crawled",
                "bytes_downloaded",
                "progress",
                "broken_links_found",
            ]
        )

        await asyncio.sleep(
            1.0
        )  # Standard polite delay between chunks depending on limit

    session.status = "completed"
    session.completed_at = timezone.now()
    session.message = "Crawl completed successfully."
    session.progress = 1.0
    await session.asave(update_fields=["status", "completed_at", "message", "progress"])

    # Pick #05 — flush the in-memory cardinality counter to its
    # snapshot file so dashboard reads survive a process restart.
    try:
        HLL_REGISTRY.snapshot("crawl_unique_urls")
    except Exception:
        logger.debug("HLL snapshot persistence failed")


def _parse_html(html: str, meta: CrawledPageMeta, base_url: str):
    soup = BeautifulSoup(html, "lxml")

    meta.title = (
        soup.title.string.strip()[:500] if soup.title and soup.title.string else ""
    )

    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag and desc_tag.get("content"):
        meta.meta_description = str(desc_tag["content"]).strip()

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    if canonical_tag and canonical_tag.get("href"):
        meta.canonical_url = str(canonical_tag["href"])[:2000]

    robots_tag = soup.find("meta", attrs={"name": "robots"})
    if robots_tag and robots_tag.get("content"):
        meta.robots_meta = str(robots_tag["content"])[:200]

    viewport_tag = soup.find("meta", attrs={"name": "viewport"})
    meta.has_viewport = bool(viewport_tag)

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        meta.og_title = str(og_title["content"])[:500]

    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content"):
        meta.og_description = str(og_desc["content"])

    h1_tags = soup.find_all("h1")
    meta.h1_count = len(h1_tags)
    if h1_tags:
        meta.h1_text = str(h1_tags[0].get_text(strip=True))[:500]

    # Clean text extraction
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    clean_text = " ".join(text.split())
    meta.extracted_text = clean_text
    meta.word_count = len(clean_text.split())

    if len(html) > 0:
        meta.content_to_html_ratio = len(clean_text) / len(html)

    # Pick #12 — SHA-256 fingerprint helper applies NFKC first so two
    # canonically-equivalent texts (different Unicode encodings) map to
    # the same hash. Empty / very short bodies return None and the
    # column stays empty (read-side dedup skips trivial pages).
    digest = content_fingerprint(clean_text)
    meta.content_hash = digest or ""

    # Images
    images = soup.find_all("img")
    meta.img_total = len(images)
    meta.img_missing_alt = sum(1 for img in images if not img.get("alt"))

    # Structured Data (JSON-LD)
    schema_types = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            if not script.string:
                continue
            data = json.loads(str(script.string))
            if isinstance(data, dict) and "@type" in data:
                schema_types.append(data["@type"])
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "@type" in item:
                        schema_types.append(item["@type"])
        except Exception:
            logger.debug("Failed to parse or process JSON-LD script tag", exc_info=True)
    meta.structured_data_types = schema_types

    # Link aggregation is bypassed for brevity but we count them.
    all_links = soup.find_all("a", href=True)
    domain_netloc = urlparse(base_url).netloc

    internal_count = 0
    external_count = 0
    nofollow_count = 0

    for a in all_links:
        href = a.get("href")
        if not href:
            continue
        href_str = str(href).strip()
        rel = a.get("rel")
        rel_list = rel if isinstance(rel, list) else [rel] if rel else []
        if "nofollow" in rel_list:
            nofollow_count += 1

        parsed_href = urlparse(urljoin(base_url, href_str))
        if parsed_href.netloc == domain_netloc:
            internal_count += 1
        else:
            external_count += 1

    meta.internal_link_count = internal_count
    meta.external_link_count = external_count
    meta.nofollow_link_count = nofollow_count


def _save_page_meta(meta: CrawledPageMeta):
    if not CrawledPageMeta.objects.filter(
        session=meta.session, normalized_url=meta.normalized_url
    ).exists():
        meta.save()
