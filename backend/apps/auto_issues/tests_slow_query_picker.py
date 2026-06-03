"""Convention-named SimpleTestCase coverage for services/slow_query_picker.py.

The mutation gate discovers ONLY this exact filename
(``tests_slow_query_picker.py`` next to ``slow_query_picker.py``).  The picker
reads the Postgres ``pg_stat_statements`` view, so the cursor is mocked here and
no real database query runs.  The pure helpers are exercised directly.

Exact-value assertions pin the diff-scoped literals so mutants that shift a
severity band (5000 / 1000 / 250), a noise fragment, or the [0, 1] priority
clamp are killed rather than left surviving (which would wedge the gate).
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import slow_query_picker as sq
from apps.auto_issues.services.slow_query_picker import SlowQuery


def _q(**kwargs) -> SlowQuery:
    defaults = dict(
        queryid=42,
        query="SELECT * FROM content",
        calls=3,
        total_exec_ms=900.0,
        mean_exec_ms=300.0,
        max_exec_ms=500.0,
    )
    defaults.update(kwargs)
    return SlowQuery(**defaults)


class IsAppQueryTests(SimpleTestCase):
    def test_plain_app_query_is_kept(self) -> None:
        self.assertTrue(sq._is_app_query("SELECT id FROM content_page"))

    def test_pg_stat_fragment_is_rejected(self) -> None:
        self.assertFalse(sq._is_app_query("SELECT * FROM pg_stat_activity"))

    def test_information_schema_fragment_is_rejected(self) -> None:
        self.assertFalse(sq._is_app_query("SELECT * FROM information_schema.tables"))

    def test_match_is_case_insensitive(self) -> None:
        self.assertFalse(sq._is_app_query("SELECT PG_DATABASE_SIZE('x')"))

    def test_copy_public_fragment_is_rejected(self) -> None:
        # New noise fragment: pg_dump / restore COPY statements are not app bugs.
        self.assertFalse(sq._is_app_query("COPY public.content_page (id) TO STDOUT"))

    def test_issue_events_issue_fragment_is_rejected(self) -> None:
        # New noise fragment: GlitchTip's issue_events_issue join is infra, not app.
        self.assertFalse(
            sq._is_app_query("SELECT * FROM issue_events_issue WHERE id = 1")
        )

    def test_new_noise_fragments_present_in_filter_list(self) -> None:
        # Pins the exact literal strings so a string mutant on either fragment
        # is killed even if no query text happens to contain it.
        self.assertIn("copy public.", sq._NOISE_FRAGMENTS)
        self.assertIn("issue_events_issue", sq._NOISE_FRAGMENTS)


class SeverityBandTests(SimpleTestCase):
    """Exact band edges: >=5000 critical, >=1000 high, >=250 medium, else low."""

    def test_critical_at_5000_exact(self) -> None:
        self.assertEqual(sq._severity_for(_q(mean_exec_ms=5000.0)), AutoIssue.SEVERITY_CRITICAL)

    def test_high_just_below_critical(self) -> None:
        self.assertEqual(sq._severity_for(_q(mean_exec_ms=4999.0)), AutoIssue.SEVERITY_HIGH)

    def test_high_at_1000_exact(self) -> None:
        self.assertEqual(sq._severity_for(_q(mean_exec_ms=1000.0)), AutoIssue.SEVERITY_HIGH)

    def test_medium_just_below_high(self) -> None:
        self.assertEqual(sq._severity_for(_q(mean_exec_ms=999.0)), AutoIssue.SEVERITY_MEDIUM)

    def test_medium_at_250_exact(self) -> None:
        self.assertEqual(sq._severity_for(_q(mean_exec_ms=250.0)), AutoIssue.SEVERITY_MEDIUM)

    def test_low_just_below_medium(self) -> None:
        self.assertEqual(sq._severity_for(_q(mean_exec_ms=249.0)), AutoIssue.SEVERITY_LOW)


class StableExternalIdTests(SimpleTestCase):
    def test_id_is_deterministic_16_hex_chars(self) -> None:
        first = sq._stable_external_id(_q(queryid=7))
        second = sq._stable_external_id(_q(queryid=7))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)

    def test_different_queryids_give_different_ids(self) -> None:
        self.assertNotEqual(
            sq._stable_external_id(_q(queryid=1)),
            sq._stable_external_id(_q(queryid=2)),
        )


class FormatTitleTests(SimpleTestCase):
    def test_title_collapses_whitespace_and_includes_mean_and_calls(self) -> None:
        title = sq._format_title(
            _q(query="SELECT   a\n  FROM   t", mean_exec_ms=300.4, calls=5)
        )
        self.assertEqual(title, "Slow query: SELECT a FROM t mean 300ms (5 calls)")


class UpsertSourceTests(SimpleTestCase):
    """The picker tags rows with SOURCE_PG_STAT (was SOURCE_AGENT before the fix)."""

    def test_upsert_uses_pg_stat_source(self) -> None:
        captured: dict = {}

        def _fake_upsert(**kwargs):
            captured.update(kwargs)
            return (MagicMock(), "created")

        with patch.object(sq, "upsert_dedup", side_effect=_fake_upsert):
            sq._upsert_slow_query(_q(queryid=99), 0.5)

        self.assertEqual(captured["source"], AutoIssue.SOURCE_PG_STAT)
        # Guard against a regression back to the old generic agent source.
        self.assertNotEqual(captured["source"], AutoIssue.SOURCE_AGENT)


class PriorityScoreTests(SimpleTestCase):
    def test_zero_when_max_total_non_positive(self) -> None:
        self.assertEqual(sq._priority_score(_q(total_exec_ms=10.0), 0.0), 0.0)

    def test_ratio_when_below_max(self) -> None:
        self.assertEqual(sq._priority_score(_q(total_exec_ms=50.0), 200.0), 0.25)

    def test_clamped_to_one_when_over_max(self) -> None:
        self.assertEqual(sq._priority_score(_q(total_exec_ms=400.0), 200.0), 1.0)


@contextmanager
def _mock_cursor(rows):
    """Patch the module connection so .cursor() yields a cursor over ``rows``."""
    cur = MagicMock()
    cur.fetchall.return_value = rows
    cur.__enter__.return_value = cur
    cur.__exit__.return_value = False
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = cur
    with patch.object(sq, "connection", fake_conn):
        yield cur


class FetchSlowQueriesTests(SimpleTestCase):
    def test_noise_rows_are_filtered_out(self) -> None:
        rows = [
            (1, "SELECT * FROM pg_stat_activity", 2, 900.0, 450.0, 500.0),
            (2, "SELECT id FROM content_page", 3, 600.0, 200.0, 250.0),
        ]
        with _mock_cursor(rows):
            out = sq._fetch_slow_queries(250.0, 10)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].queryid, 2)

    def test_cursor_error_returns_empty_list(self) -> None:
        with _mock_cursor([]) as cur:
            cur.execute.side_effect = RuntimeError("view missing")
            out = sq._fetch_slow_queries(250.0, 10)
        self.assertEqual(out, [])


class PickSlowQueriesTests(SimpleTestCase):
    def test_empty_fetch_returns_zeroed_contract(self) -> None:
        with patch.object(sq, "_fetch_slow_queries", return_value=[]):
            result = sq.pick_slow_queries()
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

    def test_promotes_and_aggregates_outcomes(self) -> None:
        queries = [
            _q(queryid=1, total_exec_ms=1000.0),
            _q(queryid=2, total_exec_ms=500.0),
        ]
        with patch.object(sq, "_fetch_slow_queries", return_value=queries), patch.object(
            sq, "_upsert_slow_query", return_value="created"
        ):
            result = sq.pick_slow_queries(limit=10)
        self.assertEqual(result["fetched"], 2)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["promoted"], 2)
        self.assertEqual(result["status"], "ok")

    def test_limit_caps_number_promoted(self) -> None:
        queries = [_q(queryid=i, total_exec_ms=float(100 * (i + 1))) for i in range(5)]
        with patch.object(sq, "_fetch_slow_queries", return_value=queries), patch.object(
            sq, "_upsert_slow_query", return_value="created"
        ) as upsert:
            result = sq.pick_slow_queries(limit=2)
        self.assertEqual(upsert.call_count, 2)
        self.assertEqual(result["promoted"], 2)
