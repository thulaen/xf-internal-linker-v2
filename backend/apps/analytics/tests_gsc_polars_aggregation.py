"""Parity tests for the Polars-backed GSC TF-IDF aggregator helper.

The new ``_aggregate_gsc_term_records`` replaces the nested-defaultdict loop
inside ``refresh_gsc_query_tfidf``. These tests pin its output against a
verbatim re-implementation of the legacy aggregator so a future change to the
Polars block is caught immediately.
"""

from __future__ import annotations

from collections import defaultdict

from django.test import SimpleTestCase

from apps.analytics.gsc_query_vocab import _aggregate_gsc_term_records, _tokenize_query


def _legacy_aggregate(records):
    """Verbatim reproduction of the pre-Polars nested-dict aggregator."""
    page_term_clicks: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in records:
        page_id = int(record["page_id"])
        token = str(record["token"])
        clicks = int(record["clicks"])
        page_term_clicks[page_id][token] += clicks
    token_pages: dict[str, set[int]] = defaultdict(set)
    for page_id, term_clicks in page_term_clicks.items():
        for token in term_clicks:
            token_pages[token].add(page_id)
    document_frequency = {token: len(pages) for token, pages in token_pages.items()}
    return page_term_clicks, document_frequency


def _to_plain(d):
    return {k: dict(v) for k, v in d.items()}


class GscPolarsAggregationParityTests(SimpleTestCase):
    """Polars output must equal the legacy nested-dict loop."""

    def test_empty_records_returns_empty_dicts(self):
        ptc, df = _aggregate_gsc_term_records([])
        self.assertEqual(_to_plain(ptc), {})
        self.assertEqual(dict(df), {})

    def test_single_record(self):
        records = [{"page_id": 1, "token": "shoes", "clicks": 10}]
        ptc, df = _aggregate_gsc_term_records(records)
        self.assertEqual(_to_plain(ptc), {1: {"shoes": 10}})
        self.assertEqual(dict(df), {"shoes": 1})

    def test_multiple_clicks_same_page_same_token_sum(self):
        records = [
            {"page_id": 1, "token": "shoes", "clicks": 10},
            {"page_id": 1, "token": "shoes", "clicks": 5},
            {"page_id": 1, "token": "shoes", "clicks": 3},
        ]
        ptc, df = _aggregate_gsc_term_records(records)
        self.assertEqual(_to_plain(ptc), {1: {"shoes": 18}})
        self.assertEqual(dict(df), {"shoes": 1})

    def test_distinct_pages_lift_doc_frequency(self):
        records = [
            {"page_id": 1, "token": "shoes", "clicks": 10},
            {"page_id": 2, "token": "shoes", "clicks": 5},
            {"page_id": 3, "token": "shoes", "clicks": 1},
        ]
        ptc, df = _aggregate_gsc_term_records(records)
        self.assertEqual(_to_plain(ptc), {1: {"shoes": 10}, 2: {"shoes": 5}, 3: {"shoes": 1}})
        self.assertEqual(dict(df), {"shoes": 3})

    def test_same_page_same_token_does_not_double_count_doc_freq(self):
        records = [
            {"page_id": 1, "token": "shoes", "clicks": 10},
            {"page_id": 1, "token": "shoes", "clicks": 5},
        ]
        ptc, df = _aggregate_gsc_term_records(records)
        self.assertEqual(dict(df), {"shoes": 1})

    def test_multiple_tokens_per_page(self):
        records = [
            {"page_id": 1, "token": "running", "clicks": 5},
            {"page_id": 1, "token": "shoes", "clicks": 10},
            {"page_id": 1, "token": "nike", "clicks": 7},
            {"page_id": 2, "token": "shoes", "clicks": 3},
            {"page_id": 2, "token": "boots", "clicks": 8},
        ]
        ptc, df = _aggregate_gsc_term_records(records)
        legacy_ptc, legacy_df = _legacy_aggregate(records)
        self.assertEqual(_to_plain(ptc), _to_plain(legacy_ptc))
        self.assertEqual(dict(df), legacy_df)

    def test_parity_against_legacy_random_input(self):
        import random

        rng = random.Random(123)
        tokens = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
        records = []
        for _ in range(5000):
            records.append(
                {
                    "page_id": rng.randrange(50),
                    "token": rng.choice(tokens),
                    "clicks": rng.randrange(0, 100),
                }
            )
        ptc, df = _aggregate_gsc_term_records(records)
        legacy_ptc, legacy_df = _legacy_aggregate(records)
        self.assertEqual(_to_plain(ptc), _to_plain(legacy_ptc))
        self.assertEqual(dict(df), legacy_df)

    def test_realistic_tokenisation_pipeline(self):
        """End-to-end: simulate the upstream tokeniser feeding the aggregator."""
        raw_inputs = [
            (1, "best running shoes", 12),
            (1, "running shoes review", 7),
            (2, "best running shoes", 5),
            (3, "boots winter waterproof", 9),
            (3, "running shoes", 4),
        ]
        records = []
        for page_id, query, clicks in raw_inputs:
            for token in _tokenize_query(query):
                records.append({"page_id": page_id, "token": token, "clicks": clicks})
        ptc, df = _aggregate_gsc_term_records(records)
        legacy_ptc, legacy_df = _legacy_aggregate(records)
        self.assertEqual(_to_plain(ptc), _to_plain(legacy_ptc))
        self.assertEqual(dict(df), legacy_df)
