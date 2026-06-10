"""Convention-named SimpleTestCase coverage for services/glitchtip_perf_picker.py.

GlitchTip is Sentry-API-compatible. Its *errors* already reach AutoIssues via
the audit_errorlog mirror + glitchtip_picker. This picker closes the remaining
gap: GlitchTip *performance transactions* (slow endpoints / jobs) that never
raise an exception but get progressively slower.

The picker reads GlitchTip's transaction-events API (isolated behind
``_fetch_glitchtip_transactions`` so it is mocked here and no live HTTP runs).
The pure pipeline operates over already-fetched transaction dicts — mirroring
how ``slow_query_picker`` separates the DB read from the filing logic.

Exact-value assertions pin the diff-scoped literals so a mutant that shifts a
severity band (5000 / 1000 / 250 ms), the slow-only threshold, or the [0, 1]
priority clamp is killed rather than left surviving.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import glitchtip_perf_picker as gp
from apps.auto_issues.services.glitchtip_perf_picker import SlowTransaction


def _t(**kwargs) -> SlowTransaction:
    defaults = dict(
        transaction="GET /api/suggestions/",
        duration_ms=900.0,
        count=12,
        endpoint="/api/suggestions/",
    )
    defaults.update(kwargs)
    return SlowTransaction(**defaults)


class ParseTransactionsTests(SimpleTestCase):
    """Maps a Sentry-style events row to a SlowTransaction, slow-only filtered."""

    def test_fast_transactions_below_threshold_are_dropped(self) -> None:
        rows = [
            {"transaction": "GET /fast/", "p95(transaction.duration)": 50.0, "count()": 3},
            {"transaction": "GET /slow/", "p95(transaction.duration)": 800.0, "count()": 9},
        ]
        out = gp._parse_transactions(rows, min_ms=gp._MIN_DURATION_MS)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].transaction, "GET /slow/")
        self.assertEqual(out[0].duration_ms, 800.0)
        self.assertEqual(out[0].count, 9)

    def test_exact_threshold_is_kept(self) -> None:
        rows = [{"transaction": "GET /edge/", "p95(transaction.duration)": 250.0, "count()": 1}]
        out = gp._parse_transactions(rows, min_ms=250.0)
        self.assertEqual(len(out), 1)

    def test_just_below_threshold_is_dropped(self) -> None:
        rows = [{"transaction": "GET /edge/", "p95(transaction.duration)": 249.0, "count()": 1}]
        out = gp._parse_transactions(rows, min_ms=250.0)
        self.assertEqual(out, [])

    def test_missing_or_malformed_fields_do_not_crash(self) -> None:
        rows = [
            {},  # no transaction name, no duration
            {"transaction": "GET /x/", "p95(transaction.duration)": None, "count()": None},
            {"transaction": "", "p95(transaction.duration)": 5000.0},
        ]
        out = gp._parse_transactions(rows, min_ms=250.0)
        self.assertEqual(out, [])


class SeverityBandTests(SimpleTestCase):
    """Exact band edges: >=5000 critical, >=1000 high, >=250 medium, else low."""

    def test_critical_at_5000_exact(self) -> None:
        self.assertEqual(gp._severity_for(_t(duration_ms=5000.0)), AutoIssue.SEVERITY_CRITICAL)

    def test_high_just_below_critical(self) -> None:
        self.assertEqual(gp._severity_for(_t(duration_ms=4999.0)), AutoIssue.SEVERITY_HIGH)

    def test_high_at_1000_exact(self) -> None:
        self.assertEqual(gp._severity_for(_t(duration_ms=1000.0)), AutoIssue.SEVERITY_HIGH)

    def test_medium_just_below_high(self) -> None:
        self.assertEqual(gp._severity_for(_t(duration_ms=999.0)), AutoIssue.SEVERITY_MEDIUM)

    def test_medium_at_250_exact(self) -> None:
        self.assertEqual(gp._severity_for(_t(duration_ms=250.0)), AutoIssue.SEVERITY_MEDIUM)

    def test_low_just_below_medium(self) -> None:
        self.assertEqual(gp._severity_for(_t(duration_ms=249.0)), AutoIssue.SEVERITY_LOW)


class StableExternalIdTests(SimpleTestCase):
    def test_id_is_deterministic_16_hex_chars(self) -> None:
        first = gp._stable_external_id(_t(transaction="GET /a/"))
        second = gp._stable_external_id(_t(transaction="GET /a/"))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)

    def test_different_transactions_give_different_ids(self) -> None:
        self.assertNotEqual(
            gp._stable_external_id(_t(transaction="GET /a/")),
            gp._stable_external_id(_t(transaction="GET /b/")),
        )


class FormatTitleTests(SimpleTestCase):
    def test_title_includes_transaction_name_and_duration_ms(self) -> None:
        title = gp._format_title(_t(transaction="GET /api/suggestions/", duration_ms=912.4, count=7))
        self.assertIn("GET /api/suggestions/", title)
        self.assertIn("912ms", title)
        self.assertIn("7", title)


class PriorityScoreTests(SimpleTestCase):
    def test_zero_when_max_duration_non_positive(self) -> None:
        self.assertEqual(gp._priority_score(_t(duration_ms=10.0), 0.0), 0.0)

    def test_ratio_when_below_max(self) -> None:
        self.assertEqual(gp._priority_score(_t(duration_ms=50.0), 200.0), 0.25)

    def test_clamped_to_one_when_over_max(self) -> None:
        self.assertEqual(gp._priority_score(_t(duration_ms=400.0), 200.0), 1.0)


class UpsertTransactionTests(SimpleTestCase):
    """The picker tags rows with SOURCE_GLITCHTIP under the performance category."""

    def test_upsert_uses_glitchtip_source_and_performance_category(self) -> None:
        captured: dict = {}

        def _fake_upsert(**kwargs):
            captured.update(kwargs)
            return (MagicMock(), "created")

        with patch.object(gp, "upsert_dedup", side_effect=_fake_upsert):
            gp._upsert_transaction(_t(transaction="GET /api/x/", duration_ms=1200.0), 0.5)

        self.assertEqual(captured["source"], AutoIssue.SOURCE_GLITCHTIP)
        self.assertEqual(captured["category_key"], "performance")
        # Severity scales with slowness: 1200 ms is HIGH.
        self.assertEqual(captured["severity"], AutoIssue.SEVERITY_HIGH)
        # Title carries the transaction name + duration so a picking agent has context.
        self.assertIn("GET /api/x/", captured["title"])
        self.assertIn("1200ms", captured["title"])


class PickSlowestTransactionsTests(SimpleTestCase):
    def test_empty_fetch_returns_zeroed_contract(self) -> None:
        with patch.object(gp, "_fetch_glitchtip_transactions", return_value=[]):
            result = gp.pick_slowest_glitchtip_transactions()
        self.assertEqual(
            result,
            {
                "status": "ok",
                "fetched": 0,
                "promoted": 0,
                "created": 0,
                "merged": 0,
                "updated": 0,
            },
        )

    def test_promotes_slowest_and_severity_scales(self) -> None:
        rows = [
            {"transaction": "GET /critical/", "p95(transaction.duration)": 6000.0, "count()": 4},
            {"transaction": "GET /medium/", "p95(transaction.duration)": 300.0, "count()": 9},
            {"transaction": "GET /fast/", "p95(transaction.duration)": 10.0, "count()": 99},
        ]
        captured: list = []

        def _fake_upsert(**kwargs):
            captured.append(kwargs)
            return (MagicMock(), "created")

        with patch.object(gp, "_fetch_glitchtip_transactions", return_value=rows), patch.object(
            gp, "upsert_dedup", side_effect=_fake_upsert
        ):
            result = gp.pick_slowest_glitchtip_transactions(limit=10)

        # Only the two slow transactions are filed; the fast one is dropped.
        self.assertEqual(result["fetched"], 2)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["promoted"], 2)
        # The 6000 ms transaction is CRITICAL; the 300 ms one is MEDIUM.
        sev_by_duration = {c["severity"] for c in captured}
        self.assertIn(AutoIssue.SEVERITY_CRITICAL, sev_by_duration)
        self.assertIn(AutoIssue.SEVERITY_MEDIUM, sev_by_duration)

    def test_limit_caps_number_promoted(self) -> None:
        rows = [
            {"transaction": f"GET /t{i}/", "p95(transaction.duration)": float(300 + i * 100), "count()": 1}
            for i in range(5)
        ]
        with patch.object(gp, "_fetch_glitchtip_transactions", return_value=rows), patch.object(
            gp, "_upsert_transaction", return_value="created"
        ) as upsert:
            result = gp.pick_slowest_glitchtip_transactions(limit=2)
        self.assertEqual(upsert.call_count, 2)
        self.assertEqual(result["promoted"], 2)

    def test_idempotent_rerun_reports_updated_not_created(self) -> None:
        """A second run of the same slow transaction is an 'updated' outcome,
        proving dedup via the canonical fingerprint rather than a duplicate row."""
        rows = [{"transaction": "GET /slow/", "p95(transaction.duration)": 900.0, "count()": 5}]
        with patch.object(gp, "_fetch_glitchtip_transactions", return_value=rows), patch.object(
            gp, "_upsert_transaction", return_value="updated"
        ):
            result = gp.pick_slowest_glitchtip_transactions(limit=10)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["promoted"], 1)


class FetchGlitchtipTransactionsTests(SimpleTestCase):
    """The HTTP boundary returns [] (never raises) when GlitchTip is unreachable
    or env vars are unset — exactly how slow_query_picker swallows a missing view."""

    def test_returns_empty_when_env_vars_missing(self) -> None:
        with patch.object(gp, "_glitchtip_perf_env", return_value=("", "", "", "")):
            out = gp._fetch_glitchtip_transactions(limit=10)
        self.assertEqual(out, [])

    def test_returns_empty_on_request_exception(self) -> None:
        import requests

        with patch.object(
            gp, "_glitchtip_perf_env",
            return_value=("http://glitchtip:8000", "tok", "org", "proj"),
        ), patch("requests.get", side_effect=requests.RequestException("boom")):
            out = gp._fetch_glitchtip_transactions(limit=10)
        self.assertEqual(out, [])

    def test_parses_sentry_events_data_envelope(self) -> None:
        import requests

        payload = {"data": [{"transaction": "GET /x/", "p95(transaction.duration)": 700.0, "count()": 3}]}
        fake_resp = MagicMock()
        fake_resp.json.return_value = payload
        fake_resp.raise_for_status.return_value = None
        with patch.object(
            gp, "_glitchtip_perf_env",
            return_value=("http://glitchtip:8000", "tok", "org", "proj"),
        ), patch("requests.get", return_value=fake_resp):
            out = gp._fetch_glitchtip_transactions(limit=10)
        self.assertEqual(out, payload["data"])
