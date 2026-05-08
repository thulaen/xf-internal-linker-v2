"""Tests for the pure-function helpers extracted from analytics/sync.py.

These helpers replaced ~700 lines of inlined try/except/dict-literal
boilerplate across 11 long ``run_*``/``compute_*``/``_refresh_*``
entrypoints. Each is independently testable in ``SimpleTestCase``
(no DB) so a future tweak to a coefficient or threshold shows up here
before it ships.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.analytics.sync import (
    _aggregate_matomo_suggestion_totals,
    _build_content_value_kwargs,
    _build_content_value_term_inputs,
    _build_engagement_term_inputs,
    _build_ga4_defaults,
    _CONTENT_VALUE_NORMALIZED_FLOOR,
    _CONTENT_VALUE_NORMALIZED_RANGE,
    _CONTENT_VALUE_SINGLE_ITEM_SCORE,
    _CONTENT_VALUE_TERM_SPEC,
    _engagement_term_contribution,
    _ENGAGEMENT_NORMALIZED_FLOOR,
    _ENGAGEMENT_NORMALIZED_RANGE,
    _ENGAGEMENT_QUALITY_TERM_SPEC,
    _ENGAGEMENT_SINGLE_ITEM_SCORE,
    _ga4_row_key,
    _normalise_content_value_score,
    _normalise_engagement_score,
    _source_label_for,
    _term_contribution,
    compute_content_value_breakdown,
    compute_content_value_raw,
    compute_engagement_quality_breakdown,
)


class SourceLabelForTests(SimpleTestCase):
    """``_source_label_for`` maps a suggestion's host content-type to wp/xf."""

    def _suggestion_with(self, content_type: str):
        s = mock.Mock()
        s.host = mock.Mock()
        s.host.content_type = content_type
        return s

    def test_wp_post_label_wordpress(self):
        self.assertEqual(
            _source_label_for(self._suggestion_with("wp_post")), "wordpress"
        )

    def test_wp_page_label_wordpress(self):
        self.assertEqual(
            _source_label_for(self._suggestion_with("wp_page")), "wordpress"
        )

    def test_xf_thread_label_xenforo(self):
        self.assertEqual(
            _source_label_for(self._suggestion_with("xf_thread")), "xenforo"
        )

    def test_unknown_label_xenforo_fallback(self):
        # Anything not starting with "wp_" defaults to xenforo (the historical
        # contract — XenForo predated the WordPress importer).
        self.assertEqual(
            _source_label_for(self._suggestion_with("misc_content")), "xenforo"
        )


class EngagementTermContributionTests(SimpleTestCase):
    """The signed-multiplier helper used by every engagement term row."""

    def test_positive_sign(self):
        self.assertEqual(_engagement_term_contribution(0.5, 0.20, "+"), 0.10)

    def test_negative_sign(self):
        self.assertEqual(_engagement_term_contribution(0.5, 0.20, "-"), -0.10)

    def test_zero_value(self):
        self.assertEqual(_engagement_term_contribution(0.0, 0.50, "+"), 0.0)


class TermContributionTests(SimpleTestCase):
    """The kind-aware multiplier used by every content-value term row."""

    def test_log1p_kind(self):
        # log1p(0)=0; log1p(e-1)=1
        import math

        self.assertEqual(_term_contribution(0.0, 0.40, "+", 0.0, "log1p"), 0.0)
        self.assertAlmostEqual(
            _term_contribution(math.e - 1, 0.40, "+", 0.0, "log1p"),
            0.40,
        )

    def test_raw_pct_kind(self):
        self.assertEqual(_term_contribution(0.5, 0.20, "+", 100.0, "raw_pct"), 10.0)

    def test_rate_kind(self):
        self.assertAlmostEqual(_term_contribution(0.4, 0.10, "+", 10.0, "rate"), 0.4)

    def test_negative_sign_flips_magnitude(self):
        self.assertEqual(_term_contribution(0.5, 0.05, "-", 10.0, "rate"), -0.25)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            _term_contribution(0.0, 0.0, "+", 0.0, "wat")


class BuildContentValueTermInputsTests(SimpleTestCase):
    """``_build_content_value_term_inputs`` divides safely by ``max(views, 1)``."""

    def test_zero_views_uses_safe_divisor(self):
        # All rates should be 0.0 when destination_views=0 and engaged=0/...
        inputs = _build_content_value_term_inputs(
            gsc_clicks=10,
            gsc_ctr=0.05,
            destination_views=0,
            engaged_sessions=0,
            conversions=0,
            telemetry_clicks=0,
            quick_exit_sessions=0,
            dwell_30s_sessions=0,
            dwell_60s_sessions=0,
        )
        self.assertEqual(inputs["engagement_rate"], 0.0)
        self.assertEqual(inputs["click_rate"], 0.0)
        # But the raw counts pass through.
        self.assertEqual(inputs["gsc_clicks"], 10.0)
        self.assertEqual(inputs["gsc_ctr"], 0.05)

    def test_full_inputs_compute_rates(self):
        inputs = _build_content_value_term_inputs(
            gsc_clicks=100,
            gsc_ctr=0.10,
            destination_views=200,
            engaged_sessions=50,
            conversions=10,
            telemetry_clicks=20,
            quick_exit_sessions=10,
            dwell_30s_sessions=40,
            dwell_60s_sessions=30,
        )
        self.assertEqual(inputs["engagement_rate"], 0.25)
        self.assertEqual(inputs["conversion_rate"], 0.05)
        self.assertEqual(inputs["click_rate"], 0.10)
        self.assertEqual(inputs["dwell_30s_rate"], 0.20)
        self.assertEqual(inputs["dwell_60s_rate"], 0.15)
        self.assertEqual(inputs["quick_exit_rate"], 0.05)

    def test_keys_match_term_spec(self):
        # Every spec name has an input key; otherwise the breakdown loop raises KeyError.
        inputs = _build_content_value_term_inputs(
            gsc_clicks=1,
            gsc_ctr=0.0,
            destination_views=1,
            engaged_sessions=0,
            conversions=0,
            telemetry_clicks=0,
            quick_exit_sessions=0,
            dwell_30s_sessions=0,
            dwell_60s_sessions=0,
        )
        for name, _w, _s, _m, _k in _CONTENT_VALUE_TERM_SPEC:
            self.assertIn(name, inputs, f"Missing input key: {name}")


class BuildEngagementTermInputsTests(SimpleTestCase):
    """``_build_engagement_term_inputs`` returns None when all inputs zero."""

    def test_all_zero_returns_none(self):
        self.assertIsNone(_build_engagement_term_inputs({}))

    def test_partial_zero_returns_dict(self):
        # destination_views > 0 → not all-zero → return a dict.
        inputs = _build_engagement_term_inputs({"destination_views": 10})
        self.assertIsNotNone(inputs)
        self.assertEqual(inputs["engagement_rate"], 0.0)

    def test_full_inputs_compute_rates(self):
        inputs = _build_engagement_term_inputs(
            {
                "destination_views": 100,
                "engaged_sessions": 60,
                "bounce_sessions": 40,
                "total_engagement_time": 18000.0,
                "sessions": 100,
                "quick_exit_sessions": 10,
                "dwell_30s_sessions": 50,
                "dwell_60s_sessions": 30,
            }
        )
        self.assertIsNotNone(inputs)
        self.assertEqual(inputs["engagement_rate"], 0.60)
        self.assertEqual(inputs["normalized_engagement_time"], 1.0)  # 180s avg → cap
        self.assertAlmostEqual(inputs["inverse_bounce"], 0.60)
        self.assertEqual(inputs["dwell_30s_rate"], 0.50)
        self.assertEqual(inputs["dwell_60s_rate"], 0.30)
        self.assertEqual(inputs["quick_exit_rate"], 0.10)

    def test_rates_clamped_to_one(self):
        # Pathological case: dwell_30s_sessions > destination_views → still 1.0
        inputs = _build_engagement_term_inputs(
            {
                "destination_views": 10,
                "dwell_30s_sessions": 100,
            }
        )
        self.assertIsNotNone(inputs)
        self.assertEqual(inputs["dwell_30s_rate"], 1.0)

    def test_keys_match_term_spec(self):
        inputs = _build_engagement_term_inputs({"destination_views": 1})
        self.assertIsNotNone(inputs)
        for name, _w, _s in _ENGAGEMENT_QUALITY_TERM_SPEC:
            self.assertIn(name, inputs, f"Missing input key: {name}")


class NormaliseContentValueScoreTests(SimpleTestCase):
    """Min-max normalisation across a set of items."""

    def test_equal_min_max_returns_single_item_score(self):
        self.assertEqual(
            _normalise_content_value_score(1.0, 1.0, 1.0),
            _CONTENT_VALUE_SINGLE_ITEM_SCORE,
        )

    def test_at_min_returns_floor(self):
        self.assertEqual(
            _normalise_content_value_score(0.0, 0.0, 10.0),
            _CONTENT_VALUE_NORMALIZED_FLOOR,
        )

    def test_at_max_returns_floor_plus_range(self):
        self.assertEqual(
            _normalise_content_value_score(10.0, 0.0, 10.0),
            _CONTENT_VALUE_NORMALIZED_FLOOR + _CONTENT_VALUE_NORMALIZED_RANGE,
        )

    def test_midpoint(self):
        self.assertAlmostEqual(
            _normalise_content_value_score(5.0, 0.0, 10.0),
            _CONTENT_VALUE_NORMALIZED_FLOOR + 0.5 * _CONTENT_VALUE_NORMALIZED_RANGE,
        )


class NormaliseEngagementScoreTests(SimpleTestCase):
    """Min-max normalisation for engagement scores."""

    def test_equal_min_max_returns_single_item_score(self):
        self.assertEqual(
            _normalise_engagement_score(0.5, 0.5, 0.5),
            _ENGAGEMENT_SINGLE_ITEM_SCORE,
        )

    def test_at_min_returns_floor(self):
        self.assertEqual(
            _normalise_engagement_score(0.0, 0.0, 1.0),
            _ENGAGEMENT_NORMALIZED_FLOOR,
        )

    def test_at_max_returns_floor_plus_range(self):
        self.assertEqual(
            _normalise_engagement_score(1.0, 0.0, 1.0),
            _ENGAGEMENT_NORMALIZED_FLOOR + _ENGAGEMENT_NORMALIZED_RANGE,
        )


class GA4RowKeyTests(SimpleTestCase):
    """``_ga4_row_key`` returns the 6-tuple used by ``merged_rows``."""

    def test_returns_six_tuple(self):
        key = _ga4_row_key(
            {
                "suggestion_id": "abc-123",
                "device_category": "mobile",
                "default_channel_group": "Organic Search",
                "source_medium": "google / organic",
                "country": "United States",
                "region": "California",
            }
        )
        self.assertEqual(
            key,
            (
                "abc-123",
                "mobile",
                "Organic Search",
                "google / organic",
                "United States",
                "California",
            ),
        )

    def test_two_rows_with_different_country_have_different_keys(self):
        base = {
            "suggestion_id": "x",
            "device_category": "desktop",
            "default_channel_group": "",
            "source_medium": "",
            "country": "US",
            "region": "",
        }
        other = dict(base, country="UK")
        self.assertNotEqual(_ga4_row_key(base), _ga4_row_key(other))


class AggregateMatomoSuggestionTotalsTests(SimpleTestCase):
    """``_aggregate_matomo_suggestion_totals`` rolls up event rows."""

    def test_sums_per_suggestion(self):
        rows = [
            ("sug-1", "suggestion_link_impression", 10),
            ("sug-1", "suggestion_link_impression", 5),
            ("sug-1", "suggestion_link_click", 2),
            ("sug-2", "suggestion_link_click", 7),
        ]
        totals = _aggregate_matomo_suggestion_totals(rows)
        self.assertEqual(totals["sug-1"]["impressions"], 15)
        self.assertEqual(totals["sug-1"]["clicks"], 2)
        self.assertEqual(totals["sug-2"]["clicks"], 7)

    def test_unknown_event_name_skipped(self):
        rows = [("sug-1", "totally_made_up_event", 99)]
        totals = _aggregate_matomo_suggestion_totals(rows)
        # Unknown event name → no entry written.
        self.assertNotIn("sug-1", totals)

    def test_phase2_signals_aggregated(self):
        rows = [
            ("sug-1", "suggestion_destination_quick_exit", 3),
            ("sug-1", "suggestion_destination_dwell_30s", 8),
            ("sug-1", "suggestion_destination_dwell_60s", 5),
        ]
        totals = _aggregate_matomo_suggestion_totals(rows)
        self.assertEqual(totals["sug-1"]["quick_exit_sessions"], 3)
        self.assertEqual(totals["sug-1"]["dwell_30s_sessions"], 8)
        self.assertEqual(totals["sug-1"]["dwell_60s_sessions"], 5)


class BuildContentValueKwargsTests(SimpleTestCase):
    """``_build_content_value_kwargs`` converts aggregator rows → raw kwargs."""

    def test_missing_keys_default_to_zero(self):
        kwargs = _build_content_value_kwargs({}, {})
        for key in (
            "gsc_clicks",
            "gsc_impressions",
            "destination_views",
            "engaged_sessions",
            "conversions",
            "telemetry_clicks",
            "quick_exit_sessions",
            "dwell_30s_sessions",
            "dwell_60s_sessions",
        ):
            self.assertEqual(kwargs[key], 0, f"Expected zero default for {key}")
        self.assertEqual(kwargs["gsc_ctr"], 0.0)

    def test_full_passthrough(self):
        telemetry = {
            "destination_views": 100,
            "engaged_sessions": 60,
            "conversions": 5,
            "clicks": 30,
            "quick_exit_sessions": 10,
            "dwell_30s_sessions": 40,
            "dwell_60s_sessions": 25,
        }
        gsc = {"clicks": 200, "ctr": 0.05, "impressions": 4000}
        kwargs = _build_content_value_kwargs(telemetry, gsc)
        self.assertEqual(kwargs["gsc_clicks"], 200)
        self.assertEqual(kwargs["gsc_ctr"], 0.05)
        self.assertEqual(kwargs["gsc_impressions"], 4000)
        self.assertEqual(kwargs["destination_views"], 100)
        self.assertEqual(kwargs["engaged_sessions"], 60)
        self.assertEqual(kwargs["telemetry_clicks"], 30)

    def test_kwargs_callable_against_compute_content_value_raw(self):
        # The whole point of this helper is that ``compute_content_value_raw(**kwargs)``
        # works without a TypeError. Verify the keys match the function signature.
        kwargs = _build_content_value_kwargs(
            {"destination_views": 10, "engaged_sessions": 5},
            {"clicks": 2, "ctr": 0.05, "impressions": 100},
        )
        result = compute_content_value_raw(**kwargs)
        self.assertIsNotNone(result)


class ComputeContentValueRawAndBreakdownParityTests(SimpleTestCase):
    """The raw + breakdown helpers MUST share the same formula bit-for-bit."""

    def test_raw_matches_breakdown_sum(self):
        kwargs = {
            "gsc_clicks": 100,
            "gsc_ctr": 0.05,
            "gsc_impressions": 4000,
            "destination_views": 200,
            "engaged_sessions": 80,
            "conversions": 10,
            "telemetry_clicks": 30,
            "quick_exit_sessions": 5,
            "dwell_30s_sessions": 60,
            "dwell_60s_sessions": 35,
        }
        raw = compute_content_value_raw(**kwargs)
        breakdown = compute_content_value_breakdown(**kwargs)
        self.assertIsNotNone(raw)
        self.assertTrue(breakdown["has_data"])
        self.assertAlmostEqual(raw, breakdown["raw"])

    def test_raw_returns_none_when_breakdown_no_data(self):
        kwargs = {
            "gsc_clicks": 0,
            "gsc_ctr": 0.0,
            "gsc_impressions": 0,
            "destination_views": 0,
            "engaged_sessions": 0,
            "conversions": 0,
            "telemetry_clicks": 0,
            "quick_exit_sessions": 0,
            "dwell_30s_sessions": 0,
            "dwell_60s_sessions": 0,
        }
        self.assertIsNone(compute_content_value_raw(**kwargs))
        self.assertFalse(compute_content_value_breakdown(**kwargs)["has_data"])


class ComputeEngagementBreakdownParityTests(SimpleTestCase):
    """Engagement raw + breakdown MUST share the same formula bit-for-bit."""

    def test_raw_matches_breakdown_sum_within_clamp_window(self):
        from apps.analytics.sync import _compute_engagement_raw_score

        telemetry = {
            "destination_views": 100,
            "engaged_sessions": 60,
            "bounce_sessions": 40,
            "total_engagement_time": 9000.0,
            "sessions": 100,
            "quick_exit_sessions": 5,
            "dwell_30s_sessions": 30,
            "dwell_60s_sessions": 20,
        }
        raw = _compute_engagement_raw_score(telemetry)
        breakdown = compute_engagement_quality_breakdown(telemetry)
        self.assertIsNotNone(raw)
        self.assertTrue(breakdown["has_data"])
        # Breakdown raw is unclamped; engagement raw is clamped to [0,1].
        # Within the historical [0,1] window they MUST match.
        self.assertGreaterEqual(breakdown["raw"], 0.0)
        self.assertLessEqual(breakdown["raw"], 1.0)
        self.assertAlmostEqual(raw, breakdown["raw"])


class BuildGA4DefaultsTests(SimpleTestCase):
    """``_build_ga4_defaults`` builds the upsert payload."""

    def _suggestion(self, content_type: str = "wp_post"):
        s = mock.Mock()
        s.destination = mock.Mock()
        s.host = mock.Mock()
        s.host.content_type = content_type
        return s

    def test_defaults_contain_all_required_keys(self):
        defaults = _build_ga4_defaults(
            suggestion=self._suggestion("wp_post"),
            algorithm_key="reco_v3",
            algorithm_version_date="2026-04-15",
            event_schema="v2",
            key_fields={
                "device_category": "desktop",
                "default_channel_group": "Organic",
                "source_medium": "google/organic",
                "country": "US",
                "region": "CA",
            },
            field_totals={
                "impressions": 10,
                "clicks": 2,
                "destination_views": 5,
                "engaged_sessions": 3,
                "conversions": 1,
                "sessions": 4,
                "total_engagement_time_seconds": 600.0,
                "event_count": 22,
                "quick_exit_sessions": 1,
                "dwell_30s_sessions": 2,
                "dwell_60s_sessions": 1,
            },
        )
        # Spot-check the most failure-prone fields:
        self.assertEqual(defaults["impressions"], 10)
        self.assertEqual(defaults["sessions"], 4)
        self.assertEqual(defaults["engaged_sessions"], 3)
        self.assertEqual(defaults["bounce_sessions"], 1)  # max(4-3, 0)
        self.assertEqual(defaults["source_label"], "wordpress")
        self.assertEqual(defaults["device_category"], "desktop")
        self.assertEqual(defaults["country"], "US")
        # avg_engagement_time_seconds = 600.0 / 4 sessions = 150.0
        self.assertEqual(defaults["avg_engagement_time_seconds"], 150.0)

    def test_zero_sessions_avg_engagement_time_is_zero(self):
        # Avoid the ZeroDivisionError when sessions=0.
        defaults = _build_ga4_defaults(
            suggestion=self._suggestion("wp_post"),
            algorithm_key="k",
            algorithm_version_date="d",
            event_schema="v2",
            key_fields={
                "device_category": "",
                "default_channel_group": "",
                "source_medium": "",
                "country": "",
                "region": "",
            },
            field_totals={
                "sessions": 0,
                "engaged_sessions": 0,
                "total_engagement_time_seconds": 0.0,
            },
        )
        self.assertEqual(defaults["avg_engagement_time_seconds"], 0.0)

    def test_xenforo_source_label(self):
        defaults = _build_ga4_defaults(
            suggestion=self._suggestion("xf_thread"),
            algorithm_key="k",
            algorithm_version_date="d",
            event_schema="v2",
            key_fields={
                "device_category": "",
                "default_channel_group": "",
                "source_medium": "",
                "country": "",
                "region": "",
            },
            field_totals={},
        )
        self.assertEqual(defaults["source_label"], "xenforo")

    def test_bounce_sessions_clamped_to_zero(self):
        # If engaged > sessions (data anomaly) bounce stays at 0, never negative.
        defaults = _build_ga4_defaults(
            suggestion=self._suggestion("wp_post"),
            algorithm_key="k",
            algorithm_version_date="d",
            event_schema="v2",
            key_fields={
                "device_category": "",
                "default_channel_group": "",
                "source_medium": "",
                "country": "",
                "region": "",
            },
            field_totals={"sessions": 5, "engaged_sessions": 10},
        )
        self.assertEqual(defaults["bounce_sessions"], 0)
