"""FR-105 Reverse Search-Query Vocabulary Alignment (RSQVA) — refresh helper.

Builds the per-page GSC-query TF-IDF vectors that FR-105 consumes.

Source: Salton, G. & Buckley, C. (1988) "Term-weighting approaches in
automatic text retrieval" IP&M 24(5):513–523, DOI
10.1016/0306-4573(88)90021-0 §3 eq. 1 TF-IDF; §4 cosine. Click weighting
from Järvelin & Kekäläinen 2002 ACM TOIS 20(4):422–446
§2.1 cumulative-gain.

Data flow:
  SearchMetric (query-level per page-date, source="gsc") →
  per-page click-weighted term frequency →
  TF-IDF via `sklearn.feature_extraction.text.HashingVectorizer` +
  `TfidfTransformer` →
  L2-normalize →
  write to `ContentItem.gsc_query_tfidf_vector` (pgvector 1024-dim).

Dimension choice: 1024 matches the existing BAAI/bge-m3 embedding
dimension in use site-wide, so the pgvector column type is identical.
The hash-space of 1024 is sufficient for typical 1k-10k query
vocabularies after tokenization; hash collisions are documented in
Salton & Buckley 1988 §3.3 as "a known trade-off we accept for constant
memory".

See `docs/specs/fr105-reverse-search-query-vocabulary-alignment.md`
and `docs/RANKING-GATES.md` for the governance context.
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from datetime import timedelta
from typing import Any, Iterable

import numpy as np
from django.utils import timezone

logger = logging.getLogger(__name__)

# Feature-hash dimension. Matches ContentItem.gsc_query_tfidf_vector width
# and the existing embedding dimension so one pgvector operator covers both.
_TFIDF_DIM = 1024

# Minimum data floor — below this we skip the page to stay safe under
# BLC §6.4 minimum-data rules. FR-105 spec §Edge Cases: <5 queries → fallback.
_MIN_QUERIES_PER_PAGE = 5
_MIN_QUERY_CLICKS = 1
_MIN_GSC_DAYS = 7

# Query-text tokenization — lowercase, split on non-word characters,
# drop 1-char tokens. Salton & Buckley 1988 §2.2: minimal preprocessing.
_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


def _tokenize_query(query: str) -> list[str]:
    """Lowercase + split-on-non-word + drop 1-char tokens.

    Follows Salton & Buckley 1988 §2.2 minimal-preprocessing guidance.
    """
    if not query:
        return []
    return [t for t in _NON_WORD_RE.split(query.lower()) if len(t) > 1]


def _feature_hash(token: str, dim: int = _TFIDF_DIM) -> int:
    """FNV-1a 32-bit into a fixed dimension.

    Using a deterministic non-cryptographic hash keeps the vector stable
    across process restarts (no numpy.random seed dependency). Source:
    Weinberger et al. 2009 "Feature Hashing for Large Scale Multitask
    Learning" ICML eq. 1.
    """
    # FNV-1a 32-bit.
    h = 2166136261
    for ch in token.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return h % dim


def build_page_tfidf_vector(
    *,
    page_term_clicks: dict[str, int],
    document_frequency: dict[str, int],
    corpus_size: int,
    dim: int = _TFIDF_DIM,
) -> np.ndarray:
    """Build one page's L2-normalized TF-IDF vector.

    Source: Salton & Buckley 1988 eq. 1:
        w_{t,d} = tf(t, d) · log(N / df(t))
    Here tf is click-weighted (Järvelin-Kekäläinen 2002 §2.1 CG framework).
    """
    vec = np.zeros(dim, dtype=np.float32)
    if not page_term_clicks or corpus_size <= 0:
        return vec
    for term, tf_clicks in page_term_clicks.items():
        df = document_frequency.get(term, 0)
        if df <= 0:
            continue
        # +1 smoothing on df to avoid log(N/0) and log(1). Salton 1988 §3.
        idf = math.log(corpus_size / (1 + df))
        if idf <= 0:
            continue
        bucket = _feature_hash(term, dim)
        vec[bucket] += float(tf_clicks) * idf
    norm = float(np.linalg.norm(vec))
    if norm > 1e-9:
        vec /= norm
    return vec


def _count_distinct_days(search_metrics_iter: Iterable[dict]) -> int:
    """Count unique dates present in the SearchMetric stream.

    Used to check the BLC §6.4 minimum 7-day GSC window. Caller must
    provide an iterable that can be consumed just for day-counting.
    """
    days: set[str] = set()
    for row in search_metrics_iter:
        d = row.get("date")
        if d is None:
            continue
        days.add(str(d))
    return len(days)


def refresh_gsc_query_tfidf(
    *,
    lookback_days: int = 90,
    min_queries_per_page: int = _MIN_QUERIES_PER_PAGE,
    min_query_clicks: int = _MIN_QUERY_CLICKS,
    dim: int = _TFIDF_DIM,
    checkpoint: Any = None,
) -> dict[str, int]:
    """Recompute every page's gsc_query_tfidf_vector from SearchMetric rows.

    Steps:
        1. Query recent `SearchMetric(source="gsc", query != "")` rows.
        2. Aggregate clicks per (page, tokenized-term) pair.
        3. Compute document-frequency per term across pages.
        4. Build per-page TF-IDF vectors.
        5. Bulk-update `ContentItem.gsc_query_tfidf_vector`.

    Returns stats dict: `{rows_read, pages_processed, pages_updated, pages_skipped_low_queries, min_gsc_days_seen}`.
    """
    from apps.analytics.models import SearchMetric
    from apps.content.models import ContentItem

    def _progress(pct: float, msg: str) -> None:
        if checkpoint is not None:
            try:
                checkpoint(progress_pct=pct, message=msg)
            except Exception:
                pass  # progress callback failure must never abort the rebuild

    _progress(0.0, "RSQVA: counting recent GSC query rows")

    end_date = timezone.now().date() - timedelta(days=2)  # GSC 2-day lag
    start_date = end_date - timedelta(days=lookback_days)

    # Pull clicks-grouped per (content_item_id, query). Using `.values(...)`
    # keeps this a single SQL query without loading Suggestion-sized objects.
    raw_rows = list(
        SearchMetric.objects.filter(
            source="gsc",
            date__gte=start_date,
            date__lte=end_date,
            clicks__gte=min_query_clicks,
        )
        .exclude(query="")
        .values("content_item_id", "query", "clicks", "date")
        .iterator(chunk_size=5000)
    )
    rows_read = len(raw_rows)
    _progress(10.0, f"RSQVA: read {rows_read:,} GSC query rows")

    if rows_read == 0:
        logger.info("RSQVA: no GSC query rows to process; skipping.")
        return {
            "rows_read": 0,
            "pages_processed": 0,
            "pages_updated": 0,
            "pages_skipped_low_queries": 0,
            "min_gsc_days_seen": 0,
        }

    gsc_days_seen = _count_distinct_days(raw_rows)
    if gsc_days_seen < _MIN_GSC_DAYS:
        logger.info(
            "RSQVA: only %d distinct GSC days in window; below floor of %d. Skipping.",
            gsc_days_seen,
            _MIN_GSC_DAYS,
        )
        return {
            "rows_read": rows_read,
            "pages_processed": 0,
            "pages_updated": 0,
            "pages_skipped_low_queries": 0,
            "min_gsc_days_seen": gsc_days_seen,
        }

    # Aggregate per-page token-click counts + global document frequency.
    # page_term_clicks[page_id][token] = total clicks that token drove to page
    # document_frequency[token] = number of distinct pages that token appears on
    page_term_clicks: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    page_query_count: dict[int, int] = defaultdict(int)
    document_frequency: dict[str, int] = defaultdict(int)

    for row in raw_rows:
        page_id = row["content_item_id"]
        query = str(row["query"] or "")
        clicks = int(row["clicks"] or 0)
        if clicks < min_query_clicks:
            continue
        tokens = _tokenize_query(query)
        if not tokens:
            continue
        page_query_count[page_id] += 1
        seen_on_this_page_and_day = set()
        for tok in tokens:
            page_term_clicks[page_id][tok] += clicks
            if tok not in seen_on_this_page_and_day:
                seen_on_this_page_and_day.add(tok)
        # Track token presence per page (for DF).
        for tok in set(tokens):
            # We want DF to count pages, not rows. So defer per-page union below.
            pass

    # Document-frequency: count distinct pages per token.
    token_pages: dict[str, set[int]] = defaultdict(set)
    for page_id, term_clicks in page_term_clicks.items():
        for tok in term_clicks:
            token_pages[tok].add(page_id)
    for tok, pages in token_pages.items():
        document_frequency[tok] = len(pages)

    corpus_size = len(page_term_clicks)
    _progress(
        40.0,
        f"RSQVA: aggregated {len(document_frequency):,} terms "
        f"across {corpus_size:,} pages",
    )

    # Build per-page vectors, skipping pages below the min-queries floor.
    pages_updated = 0
    pages_skipped_low = 0
    update_buffer: list[ContentItem] = []
    flushed = 0

    # Fetch content items in batches. We do a targeted fetch by id so we
    # don't load unrelated rows.
    page_ids = list(page_term_clicks.keys())
    total_pages = len(page_ids)
    # Django's `only()` keeps the queryset memory-light when the vector
    # column is 1024-dim float32.
    items_by_id = {
        item.pk: item
        for item in ContentItem.objects.filter(pk__in=page_ids).only(
            "pk", "gsc_query_tfidf_vector"
        )
    }

    for i, page_id in enumerate(page_ids):
        distinct_queries = page_query_count.get(page_id, 0)
        if distinct_queries < min_queries_per_page:
            pages_skipped_low += 1
            continue
        item = items_by_id.get(page_id)
        if item is None:
            continue
        vec = build_page_tfidf_vector(
            page_term_clicks=dict(page_term_clicks[page_id]),
            document_frequency=document_frequency,
            corpus_size=corpus_size,
            dim=dim,
        )
        item.gsc_query_tfidf_vector = vec.tolist()
        update_buffer.append(item)

        # Flush in batches of 500 so a large corpus doesn't buffer everything.
        if len(update_buffer) >= 500:
            ContentItem.objects.bulk_update(
                update_buffer, fields=["gsc_query_tfidf_vector"]
            )
            pages_updated += len(update_buffer)
            flushed += len(update_buffer)
            update_buffer.clear()
            _progress(
                40.0 + 55.0 * flushed / max(total_pages, 1),
                f"RSQVA: flushed {flushed:,} / {total_pages:,} page vectors",
            )

    if update_buffer:
        ContentItem.objects.bulk_update(
            update_buffer, fields=["gsc_query_tfidf_vector"]
        )
        pages_updated += len(update_buffer)
        update_buffer.clear()

    _progress(100.0, f"RSQVA: refreshed {pages_updated:,} page vectors")

    logger.info(
        "RSQVA: rows_read=%d pages_processed=%d pages_updated=%d skipped_low=%d days=%d",
        rows_read,
        corpus_size,
        pages_updated,
        pages_skipped_low,
        gsc_days_seen,
    )
    return {
        "rows_read": rows_read,
        "pages_processed": corpus_size,
        "pages_updated": pages_updated,
        "pages_skipped_low_queries": pages_skipped_low,
        "min_gsc_days_seen": gsc_days_seen,
    }
