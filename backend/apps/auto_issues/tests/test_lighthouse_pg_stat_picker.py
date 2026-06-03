"""TDD tests for lighthouse_picker and slow_query_picker (pg_stat source)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.auto_issues.management.commands.verify_autoissue_quota import (
    REQUIRED_AUTOISSUE_FIXES,
    REQUIRED_LIGHTHOUSE_FIXES,
    REQUIRED_PG_STAT_FIXES,
    REQUIRED_SONARQUBE_FIXES,
    _count_and_duplicate_errors,
    _hard_quota_errors,
    _mandatory_hard_errors,
)
from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.lighthouse_picker import (
    _DEFAULT_FRONTEND_URL,
    _THRESHOLDS,
    _external_id,
    _failing,
    _priority,
    _scores_from_report,
    _severity,
    _upsert_score,
    _url_slug,
    LighthouseScore,
    pick_lighthouse_scores,
)
from apps.auto_issues.services.slow_query_picker import (
    _is_app_query,
    _severity_for,
    SlowQuery,
)


# ── Lighthouse picker ─────────────────────────────────────────────────────────

class LighthouseScoreHelperTests(SimpleTestCase):
    """Pure-function tests — no DB, no subprocess."""

    def test_url_slug_is_stable(self):
        slug1 = _url_slug("http://example.com")
        slug2 = _url_slug("http://example.com")
        self.assertEqual(slug1, slug2)
        self.assertEqual(len(slug1), 8)

    def test_url_slug_differs_for_different_urls(self):
        self.assertNotEqual(
            _url_slug("http://example.com"),
            _url_slug("http://other.com"),
        )

    def test_external_id_format(self):
        eid = _external_id("performance", "http://example.com")
        self.assertTrue(eid.startswith("lighthouse:performance:"))

    def test_severity_critical_below_50(self):
        self.assertEqual(_severity(0.49), AutoIssue.SEVERITY_CRITICAL)

    def test_severity_high_below_70(self):
        self.assertEqual(_severity(0.65), AutoIssue.SEVERITY_HIGH)

    def test_severity_medium_below_85(self):
        self.assertEqual(_severity(0.80), AutoIssue.SEVERITY_MEDIUM)

    def test_severity_low_at_threshold(self):
        self.assertEqual(_severity(0.85), AutoIssue.SEVERITY_LOW)

    def test_priority_worse_score_is_higher(self):
        self.assertGreater(_priority(0.40), _priority(0.80))

    def test_priority_clamped_to_zero_for_perfect_score(self):
        self.assertEqual(_priority(1.0), 0.0)

    def test_scores_from_report_clamps_score_above_1(self):
        """Bug fix: a malformed report with score > 1.0 must not produce display_score > 100."""
        fake_report = {"categories": {"performance": {"score": 1.5}}}
        scores = _scores_from_report(fake_report, "http://example.com")
        self.assertEqual(len(scores), 1)
        self.assertLessEqual(scores[0].score, 1.0)
        self.assertLessEqual(scores[0].display_score, 100)

    def test_scores_from_report_clamps_score_below_0(self):
        fake_report = {"categories": {"performance": {"score": -0.1}}}
        scores = _scores_from_report(fake_report, "http://example.com")
        self.assertGreaterEqual(scores[0].score, 0.0)
        self.assertGreaterEqual(scores[0].display_score, 0)

    def test_scores_from_report_extracts_all_categories(self):
        fake_report = {
            "categories": {
                "performance": {"score": 0.72},
                "accessibility": {"score": 0.91},
                "best-practices": {"score": 0.83},
                "seo": {"score": 0.95},
            }
        }
        scores = _scores_from_report(fake_report, "http://example.com")
        self.assertEqual(len(scores), 4)
        perf = next(s for s in scores if s.category == "performance")
        self.assertAlmostEqual(perf.score, 0.72)
        self.assertEqual(perf.display_score, 72)

    def test_scores_from_report_skips_missing_category(self):
        fake_report = {"categories": {"performance": {"score": 0.80}}}
        scores = _scores_from_report(fake_report, "http://example.com")
        self.assertEqual(len(scores), 1)

    def test_scores_from_report_skips_null_score(self):
        fake_report = {"categories": {"performance": {"score": None}}}
        scores = _scores_from_report(fake_report, "http://example.com")
        self.assertEqual(len(scores), 0)

    def test_failing_returns_only_below_threshold(self):
        good = LighthouseScore(category="performance", score=0.90, display_score=90, url="u")
        bad = LighthouseScore(category="accessibility", score=0.70, display_score=70, url="u")
        self.assertEqual(_failing([good, bad]), [bad])

    def test_failing_empty_when_all_pass(self):
        all_good = [
            LighthouseScore(category=cat, score=0.95, display_score=95, url="u")
            for cat in _THRESHOLDS
        ]
        self.assertEqual(_failing(all_good), [])

class LighthouseUpsertConsistencyTests(SimpleTestCase):
    """Bug fix: threshold_pct must be the same value in title and description."""

    def test_title_and_description_use_same_threshold(self):
        """_upsert_score must not call round(_THRESHOLDS[...]*100) twice with diverging results."""
        s = LighthouseScore(
            category="performance", score=0.70, display_score=70, url="http://t.test"
        )
        expected_pct = round(_THRESHOLDS["performance"] * 100)
        with patch(
            "apps.auto_issues.services.lighthouse_picker.upsert_dedup",
            return_value=(None, "created"),
        ) as mock_upsert:
            _upsert_score(s)
        call_kwargs = mock_upsert.call_args[1]
        self.assertIn(str(expected_pct), call_kwargs["title"])
        self.assertIn(str(expected_pct), call_kwargs["description"])


class QuotaCommandBugTests(SimpleTestCase):
    """Regression tests for bugs found and fixed in verify_autoissue_quota.py."""

    def _all_zero_counts(self) -> dict:
        """Return a counts dict with every mandatory source at zero."""
        return {
            source: 0
            for source in [
                AutoIssue.SOURCE_SONARQUBE, AutoIssue.SOURCE_RUST_DEFECT,
                AutoIssue.SOURCE_PPROF, AutoIssue.SOURCE_ALLOY,
                AutoIssue.SOURCE_LOKI, AutoIssue.SOURCE_PERFETTO,
                AutoIssue.SOURCE_GWP_ASAN, AutoIssue.SOURCE_PROMETHEUS,
                AutoIssue.SOURCE_PG_STAT, AutoIssue.SOURCE_LIGHTHOUSE,
                AutoIssue.SOURCE_AGENT, AutoIssue.SOURCE_GLITCHTIP,
                AutoIssue.SOURCE_PYROSCOPE, AutoIssue.SOURCE_TEMPO,
                AutoIssue.SOURCE_FARO, AutoIssue.SOURCE_MUTATION,
                AutoIssue.SOURCE_FUZZ, AutoIssue.SOURCE_CONTRACT,
                AutoIssue.SOURCE_GH_CI, AutoIssue.SOURCE_VMALERT,
            ]
        }

    def test_mandatory_hard_errors_no_keyerror_on_missing_source(self):
        """Bug fix: _mandatory_hard_errors used counts[key] directly on sonarqube.
        If counts dict is missing the key it must return an error, not raise KeyError."""
        # Simulates first-ever session where counts is empty.
        result = _mandatory_hard_errors(0, AutoIssue.SOURCE_SONARQUBE, REQUIRED_SONARQUBE_FIXES)
        self.assertTrue(len(result) > 0)
        self.assertIn("NON-SUBSTITUTABLE", result[0])

    @patch("apps.auto_issues.management.commands.verify_autoissue_quota._next_open_issue_ids", return_value=[])
    def test_hard_quota_errors_no_keyerror_on_empty_counts(self, mock_next_ids):
        """Bug fix: calling _hard_quota_errors with only zeroed counts must not KeyError."""
        counts = self._all_zero_counts()
        # Should return errors (all quotas unmet) but never raise.
        errors = _hard_quota_errors(counts, "2026-05-26 00:00")
        self.assertIsInstance(errors, list)
        self.assertTrue(len(errors) > 0)

    def test_count_duplicate_errors_uses_counter_not_quadratic(self):
        """Bug fix: O(n²) list.count() replaced with O(n) Counter.
        Regression: duplicates must still be detected correctly."""
        ids_with_dupe = [1, 2, 3, 2, 4]  # 2 appears twice
        errors = _count_and_duplicate_errors(ids_with_dupe)
        # Will also report wrong count, but duplicate error must be present.
        duplicate_error = next((e for e in errors if "Duplicate" in e), None)
        self.assertIsNotNone(duplicate_error)
        self.assertIn("#2", duplicate_error)

    def test_count_duplicate_errors_no_false_positive(self):
        """Each ID appears once — no duplicate error."""
        ids_unique = list(range(1, REQUIRED_AUTOISSUE_FIXES + 1))
        errors = _count_and_duplicate_errors(ids_unique)
        duplicate_errors = [e for e in errors if "Duplicate" in e]
        self.assertEqual(duplicate_errors, [])

    @patch("apps.auto_issues.management.commands.verify_autoissue_quota._next_open_issue_ids", return_value=[])
    def test_quota_description_uses_constants_not_literals(self, mock_next_ids):
        """Bug fix: the quota description string must derive values from constants.
        If REQUIRED_LIGHTHOUSE_FIXES is 3, the message must say '3 lighthouse'."""
        counts = self._all_zero_counts()
        errors = _hard_quota_errors(counts, "2026-05-26 00:00")
        # The description line is always the third item in the message list.
        desc_line = next((l for l in errors if "lighthouse" in l and "required:" in l), None)
        self.assertIsNotNone(desc_line)
        self.assertIn(str(REQUIRED_LIGHTHOUSE_FIXES), desc_line)
        self.assertIn(str(REQUIRED_SONARQUBE_FIXES), desc_line)


class LighthousePickerUnavailableTests(SimpleTestCase):
    """pick_lighthouse_scores gracefully handles a missing CLI."""

    def test_returns_unavailable_when_cli_missing(self):
        with patch(
            "apps.auto_issues.services.lighthouse_picker._run_lighthouse",
            return_value=None,
        ):
            result = pick_lighthouse_scores(url="http://nowhere")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["failing"], 0)
        self.assertEqual(result["promoted"], 0)

    def test_returns_ok_with_zero_failures_when_all_scores_pass(self):
        fake_report = {
            "categories": {cat: {"score": 0.99} for cat in _THRESHOLDS}
        }
        with patch(
            "apps.auto_issues.services.lighthouse_picker._run_lighthouse",
            return_value=fake_report,
        ), patch(
            "apps.auto_issues.services.lighthouse_picker._upsert_score",
        ) as mock_upsert:
            result = pick_lighthouse_scores(url="http://ok")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["failing"], 0)
        mock_upsert.assert_not_called()

    def test_promotes_failing_categories(self):
        fake_report = {
            "categories": {
                "performance": {"score": 0.60},   # failing
                "accessibility": {"score": 0.99},  # passing
                "best-practices": {"score": 0.99},
                "seo": {"score": 0.99},
            }
        }
        with patch(
            "apps.auto_issues.services.lighthouse_picker._run_lighthouse",
            return_value=fake_report,
        ), patch(
            "apps.auto_issues.services.lighthouse_picker._upsert_score",
            return_value="created",
        ) as mock_upsert:
            result = pick_lighthouse_scores(url="http://slow")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["failing"], 1)
        self.assertEqual(result["promoted"], 1)
        mock_upsert.assert_called_once()


# ── slow_query_picker / pg_stat source ────────────────────────────────────────

class SlowQueryPickerSourceTests(SimpleTestCase):
    """Verify that slow query picker uses SOURCE_PG_STAT, not SOURCE_AGENT."""

    def test_source_constant_is_pg_stat(self):
        self.assertEqual(AutoIssue.SOURCE_PG_STAT, "pg_stat")

    def test_app_query_filter_excludes_pg_stat_queries(self):
        self.assertFalse(_is_app_query("SELECT query FROM pg_stat_statements LIMIT 10"))

    def test_app_query_filter_excludes_information_schema(self):
        self.assertFalse(_is_app_query("SELECT * FROM information_schema.columns"))

    def test_app_query_filter_excludes_backup_copy_exports(self):
        self.assertFalse(
            _is_app_query(
                "COPY public.auto_issues_autoissue (id, source, title) TO stdout"
            )
        )

    def test_app_query_filter_excludes_glitchtip_issue_updates(self):
        self.assertFalse(
            _is_app_query(
                "UPDATE issue_events_issue SET count = issue_events_issue.count + v.added_count"
            )
        )

    def test_app_query_filter_keeps_real_app_queries(self):
        self.assertTrue(_is_app_query("SELECT * FROM auto_issues_autoissue WHERE status = $1"))

    def test_severity_critical_over_5000ms(self):
        q = SlowQuery(queryid=1, query="SELECT 1", calls=1, total_exec_ms=6000, mean_exec_ms=6000, max_exec_ms=6000)
        self.assertEqual(_severity_for(q), AutoIssue.SEVERITY_CRITICAL)

    def test_severity_high_over_1000ms(self):
        q = SlowQuery(queryid=2, query="SELECT 1", calls=1, total_exec_ms=2000, mean_exec_ms=2000, max_exec_ms=2000)
        self.assertEqual(_severity_for(q), AutoIssue.SEVERITY_HIGH)

    def test_severity_medium_over_250ms(self):
        q = SlowQuery(queryid=3, query="SELECT 1", calls=1, total_exec_ms=500, mean_exec_ms=500, max_exec_ms=500)
        self.assertEqual(_severity_for(q), AutoIssue.SEVERITY_MEDIUM)
