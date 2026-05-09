"""Parity tests for the Polars-backed Matomo aggregation in apps.analytics.sync.

These tests pin the new Polars implementation against the same shape of output
the previous defaultdict loop produced, so a future change to the Polars code
that drifts from spec is caught immediately. SimpleTestCase — no DB hits.

Each test uses a synthetic ``parsed_rows`` list (the shape produced by
``_walk_matomo_rows``) and asserts the returned nested dict matches the
expected per-suggestion field totals byte-for-byte.
"""

from __future__ import annotations

from collections import defaultdict

from django.test import SimpleTestCase

from apps.analytics.sync import (
    MATOMO_EVENT_FIELDS,
    _aggregate_matomo_suggestion_totals,
)


def _legacy_aggregate(parsed_rows):
    """The old defaultdict loop, kept verbatim as the parity oracle."""
    suggestion_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for suggestion_id, event_name, count in parsed_rows:
        if event_name not in MATOMO_EVENT_FIELDS:
            continue
        suggestion_totals[str(suggestion_id)][MATOMO_EVENT_FIELDS[event_name]] += int(count)
    return suggestion_totals


def _to_plain_dict(d):
    return {k: dict(v) for k, v in d.items()}


class MatomoAggregationParityTests(SimpleTestCase):
    """Polars output must equal the legacy loop on every synthetic fixture."""

    def test_empty_input_returns_empty_dict(self):
        self.assertEqual(_to_plain_dict(_aggregate_matomo_suggestion_totals([])), {})

    def test_single_row_one_field(self):
        rows = [("sug-A", "suggestion_link_impression", 10)]
        out = _aggregate_matomo_suggestion_totals(rows)
        self.assertEqual(_to_plain_dict(out), {"sug-A": {"impressions": 10}})

    def test_multiple_rows_same_suggestion_same_field_sum(self):
        rows = [
            ("sug-A", "suggestion_link_impression", 10),
            ("sug-A", "suggestion_link_impression", 5),
            ("sug-A", "suggestion_link_impression", 3),
        ]
        out = _aggregate_matomo_suggestion_totals(rows)
        self.assertEqual(_to_plain_dict(out), {"sug-A": {"impressions": 18}})

    def test_multiple_suggestions_multiple_fields(self):
        rows = [
            ("sug-1", "suggestion_link_impression", 10),
            ("sug-1", "suggestion_link_impression", 5),
            ("sug-1", "suggestion_link_click", 2),
            ("sug-2", "suggestion_link_click", 7),
            ("sug-2", "suggestion_destination_view", 4),
        ]
        out = _aggregate_matomo_suggestion_totals(rows)
        expected = {
            "sug-1": {"impressions": 15, "clicks": 2},
            "sug-2": {"clicks": 7, "destination_views": 4},
        }
        self.assertEqual(_to_plain_dict(out), expected)

    def test_unknown_event_names_dropped(self):
        rows = [
            ("sug-1", "totally_made_up_event", 99),
            ("sug-1", "another_bad_event", 42),
            ("sug-2", "suggestion_link_click", 7),
        ]
        out = _aggregate_matomo_suggestion_totals(rows)
        self.assertEqual(_to_plain_dict(out), {"sug-2": {"clicks": 7}})

    def test_phase2_engagement_signals(self):
        rows = [
            ("sug-1", "suggestion_destination_quick_exit", 3),
            ("sug-1", "suggestion_destination_dwell_30s", 8),
            ("sug-1", "suggestion_destination_dwell_60s", 5),
            ("sug-1", "suggestion_destination_engaged", 2),
            ("sug-1", "suggestion_destination_conversion", 1),
        ]
        out = _aggregate_matomo_suggestion_totals(rows)
        expected = {
            "sug-1": {
                "quick_exit_sessions": 3,
                "dwell_30s_sessions": 8,
                "dwell_60s_sessions": 5,
                "engaged_sessions": 2,
                "conversions": 1,
            },
        }
        self.assertEqual(_to_plain_dict(out), expected)

    def test_zero_count_rows_kept(self):
        rows = [
            ("sug-1", "suggestion_link_impression", 0),
            ("sug-1", "suggestion_link_click", 0),
        ]
        out = _aggregate_matomo_suggestion_totals(rows)
        self.assertEqual(
            _to_plain_dict(out),
            {"sug-1": {"impressions": 0, "clicks": 0}},
        )

    def test_string_count_coerced_to_int(self):
        rows = [
            ("sug-1", "suggestion_link_impression", 10),
            ("sug-1", "suggestion_link_impression", 5),
        ]
        out = _aggregate_matomo_suggestion_totals(rows)
        self.assertEqual(
            _to_plain_dict(out),
            {"sug-1": {"impressions": 15}},
        )

    def test_nested_defaultdict_get_semantics_preserved(self):
        rows = [("sug-1", "suggestion_link_impression", 10)]
        out = _aggregate_matomo_suggestion_totals(rows)
        # _persist_matomo_day_writes calls field_totals.get("clicks", 0) — must
        # not raise on absent fields.
        inner = out["sug-1"]
        self.assertEqual(inner.get("clicks", 0), 0)
        self.assertEqual(inner.get("impressions", 0), 10)

    def test_parity_against_legacy_on_bulk_random_input(self):
        import random

        rng = random.Random(42)
        events = list(MATOMO_EVENT_FIELDS.keys()) + ["unknown_event_a", "unknown_event_b"]
        rows = []
        for _ in range(2000):
            sid = f"sug-{rng.randrange(50)}"
            event = rng.choice(events)
            count = rng.randrange(0, 100)
            rows.append((sid, event, count))
        legacy_out = _legacy_aggregate(rows)
        polars_out = _aggregate_matomo_suggestion_totals(rows)
        self.assertEqual(_to_plain_dict(polars_out), _to_plain_dict(legacy_out))

    def test_parity_against_legacy_on_large_input(self):
        import random

        rng = random.Random(2026)
        events = list(MATOMO_EVENT_FIELDS.keys())
        rows = []
        for _ in range(50_000):
            sid = f"sug-{rng.randrange(500)}"
            event = rng.choice(events)
            count = rng.randrange(0, 1000)
            rows.append((sid, event, count))
        legacy_out = _legacy_aggregate(rows)
        polars_out = _aggregate_matomo_suggestion_totals(rows)
        self.assertEqual(_to_plain_dict(polars_out), _to_plain_dict(legacy_out))
