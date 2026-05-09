"""Parity tests for the Polars-backed GA4 event-row aggregator.

The new ``_accumulate_ga4_event_rows`` parses all rows from all 8 GA4 event-name
fetches into a flat list and aggregates via Polars. These tests pin its output
against a verbatim copy of the legacy nested-loop accumulator so a future change
to the Polars block is caught by parity failures.

SimpleTestCase — no DB hits. The GA4 service client is mocked via patching
``apps.analytics.sync._fetch_ga4_rows``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.analytics import sync as sync_mod
from apps.analytics.sync import (
    GA4_EVENT_FIELDS,
    _accumulate_ga4_event_rows,
    _ga4_dimensions_from_row,
    _ga4_dimension_names,
    _ga4_metric_int,
    _ga4_row_key,
    is_blocked_country,
)


def _legacy_accumulate(
    *,
    service,
    property_id: str,
    target_date,
    geo_granularity: str,
    merged_rows: dict,
    fetch_fn,
) -> int:
    """Verbatim copy of the original nested-loop accumulator.

    Used as the parity oracle. Identical to the function in sync.py before
    the Polars migration in slice 2.
    """
    rows_read = 0
    dim_names = _ga4_dimension_names(geo_granularity=geo_granularity)
    for event_name, field_name in GA4_EVENT_FIELDS.items():
        rows = fetch_fn(
            service=service,
            property_id=property_id,
            target_date=target_date,
            geo_granularity=geo_granularity,
            event_name=event_name,
            metrics=["eventCount"],
        )
        rows_read += len(rows)
        for row in rows:
            parsed = _ga4_dimensions_from_row(
                row=row,
                dimension_names=dim_names,
                geo_granularity=geo_granularity,
            )
            if is_blocked_country(parsed["country"]):
                continue
            key = _ga4_row_key(parsed)
            count = _ga4_metric_int(row, 0)
            merged_rows[key][field_name] = int(merged_rows[key][field_name]) + count
            merged_rows[key]["event_count"] = (
                int(merged_rows[key]["event_count"]) + count
            )
    return rows_read


def _empty_merged_row():
    return defaultdict(
        int,
        {
            "impressions": 0,
            "clicks": 0,
            "destination_views": 0,
            "engaged_sessions": 0,
            "conversions": 0,
            "sessions": 0,
            "event_count": 0,
            "total_engagement_time_seconds": 0.0,
            "quick_exit_sessions": 0,
            "dwell_30s_sessions": 0,
            "dwell_60s_sessions": 0,
        },
    )


def _new_merged_rows():
    return defaultdict(_empty_merged_row)


def _to_plain(d):
    return {k: dict(v) for k, v in d.items()}


def _mk_ga4_row(*, suggestion_id: str, device: str = "desktop", channel: str = "",
                source: str = "", country: str = "US", region: str = "",
                count: int) -> dict:
    """Construct a synthetic GA4 row in the exact shape returned by the API."""
    return {
        "dimensionValues": [
            {"value": "20260509"},
            {"value": suggestion_id},
            {"value": device},
            {"value": channel},
            {"value": source},
            {"value": country},
            {"value": region},
        ],
        "metricValues": [{"value": str(count)}],
    }


class GA4EventRowsParityTests(SimpleTestCase):
    """Polars accumulator must equal the legacy loop on every fixture."""

    def _run_both(self, fetch_responses: dict[str, list[dict]], geo_granularity: str = "country_region"):
        """Run both accumulators with the same canned per-event responses, return both merged_rows dicts."""

        def make_fetch(fetcher_responses):
            def fake_fetch(*, service, property_id, target_date, geo_granularity,
                           event_name, metrics):
                return fetcher_responses.get(event_name, [])
            return fake_fetch

        legacy_rows = _new_merged_rows()
        legacy_read = _legacy_accumulate(
            service=None,
            property_id="props/123",
            target_date=date(2026, 5, 9),
            geo_granularity=geo_granularity,
            merged_rows=legacy_rows,
            fetch_fn=make_fetch(fetch_responses),
        )

        polars_rows = _new_merged_rows()
        with patch.object(sync_mod, "_fetch_ga4_rows", side_effect=make_fetch(fetch_responses)):
            polars_read = _accumulate_ga4_event_rows(
                service=None,
                property_id="props/123",
                target_date=date(2026, 5, 9),
                geo_granularity=geo_granularity,
                merged_rows=polars_rows,
            )
        return legacy_rows, legacy_read, polars_rows, polars_read

    def test_empty_responses_zero_rows(self):
        legacy, lr, polars, pr = self._run_both({})
        self.assertEqual(_to_plain(legacy), _to_plain(polars))
        self.assertEqual(lr, pr)
        self.assertEqual(lr, 0)

    def test_single_event_single_row(self):
        responses = {
            "suggestion_link_impression": [
                _mk_ga4_row(suggestion_id="sug-1", count=10),
            ],
        }
        legacy, lr, polars, pr = self._run_both(responses)
        self.assertEqual(_to_plain(legacy), _to_plain(polars))
        self.assertEqual(lr, pr)

    def test_multiple_events_same_key_event_count_sums(self):
        responses = {
            "suggestion_link_impression": [
                _mk_ga4_row(suggestion_id="sug-1", count=10),
            ],
            "suggestion_link_click": [
                _mk_ga4_row(suggestion_id="sug-1", count=3),
            ],
        }
        legacy, lr, polars, pr = self._run_both(responses)
        self.assertEqual(_to_plain(legacy), _to_plain(polars))
        # event_count should be 10 + 3 = 13 in both
        key = ("sug-1", "desktop", "", "", "US", "")
        self.assertEqual(polars[key]["event_count"], 13)

    def test_blocked_country_filtered(self):
        responses = {
            "suggestion_link_impression": [
                _mk_ga4_row(suggestion_id="sug-1", country="CN", count=99),
                _mk_ga4_row(suggestion_id="sug-1", country="US", count=10),
            ],
        }
        legacy, lr, polars, pr = self._run_both(responses)
        self.assertEqual(_to_plain(legacy), _to_plain(polars))
        # CN should be filtered if blocked; verify behaviour matches legacy
        # The is_blocked_country check is identical in both.

    def test_multiple_keys_multiple_events(self):
        responses = {
            "suggestion_link_impression": [
                _mk_ga4_row(suggestion_id="sug-1", device="desktop", count=5),
                _mk_ga4_row(suggestion_id="sug-1", device="mobile", count=8),
                _mk_ga4_row(suggestion_id="sug-2", device="desktop", count=3),
            ],
            "suggestion_link_click": [
                _mk_ga4_row(suggestion_id="sug-1", device="desktop", count=1),
                _mk_ga4_row(suggestion_id="sug-2", device="desktop", count=2),
            ],
            "suggestion_destination_engaged": [
                _mk_ga4_row(suggestion_id="sug-1", device="mobile", count=4),
            ],
        }
        legacy, lr, polars, pr = self._run_both(responses)
        self.assertEqual(_to_plain(legacy), _to_plain(polars))

    def test_phase2_engagement_signals(self):
        responses = {
            "suggestion_destination_quick_exit": [
                _mk_ga4_row(suggestion_id="sug-1", count=2),
            ],
            "suggestion_destination_dwell_30s": [
                _mk_ga4_row(suggestion_id="sug-1", count=5),
            ],
            "suggestion_destination_dwell_60s": [
                _mk_ga4_row(suggestion_id="sug-1", count=3),
            ],
        }
        legacy, lr, polars, pr = self._run_both(responses)
        self.assertEqual(_to_plain(legacy), _to_plain(polars))

    def test_country_only_geo_granularity_drops_region(self):
        responses = {
            "suggestion_link_impression": [
                _mk_ga4_row(suggestion_id="sug-1", country="US", region="California", count=10),
            ],
        }
        legacy, lr, polars, pr = self._run_both(responses, geo_granularity="country")
        self.assertEqual(_to_plain(legacy), _to_plain(polars))

    def test_parity_against_legacy_on_bulk_random_input(self):
        import random

        rng = random.Random(99)
        responses: dict[str, list[dict]] = {}
        events = list(GA4_EVENT_FIELDS.keys())
        countries = ["US", "GB", "DE", "CA"]
        devices = ["desktop", "mobile", "tablet"]
        for event_name in events:
            event_rows = []
            for _ in range(rng.randrange(0, 20)):
                event_rows.append(
                    _mk_ga4_row(
                        suggestion_id=f"sug-{rng.randrange(20)}",
                        device=rng.choice(devices),
                        channel=rng.choice(["organic", "direct", ""]),
                        country=rng.choice(countries),
                        region="",
                        count=rng.randrange(0, 100),
                    )
                )
            responses[event_name] = event_rows
        legacy, lr, polars, pr = self._run_both(responses, geo_granularity="country")
        self.assertEqual(_to_plain(legacy), _to_plain(polars))
        self.assertEqual(lr, pr)
