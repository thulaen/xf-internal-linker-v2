"""Tests for the auto_issues HTTP API."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.auto_issues.models import AutoIssue, AutoIssueCategory


User = get_user_model()


class AutoIssueAPITests(TestCase):
    def setUp(self):
        # --keepdb leaves rows around between runs; isolate this suite.
        AutoIssue.objects.all().delete()
        self.admin = User.objects.create_user(
            username="admin", password="x", is_staff=True, is_superuser=True
        )
        self.viewer = User.objects.create_user(username="viewer", password="x")
        self.client = APIClient()

    def _seed(self, **overrides):
        defaults = dict(
            source=AutoIssue.SOURCE_AGENT,
            external_id="ISS-test-1",
            fingerprint="fp1",
            canonical_fingerprint="cfp1",
            title="Test issue",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_OPEN,
            priority_score=0.5,
        )
        defaults.update(overrides)
        return AutoIssue.objects.create(**defaults)

    def test_list_requires_auth(self):
        self._seed()
        resp = self.client.get("/api/auto-issues/")
        self.assertEqual(resp.status_code, 403)

    def _results(self, resp):
        """DRF paginates by default; `resp.data` is `{count, next, previous, results}`."""
        if isinstance(resp.data, dict) and "results" in resp.data:
            return resp.data["results"]
        return resp.data

    def test_list_returns_open_rows_for_viewer(self):
        self._seed()
        self.client.force_authenticate(self.viewer)
        resp = self.client.get("/api/auto-issues/")
        self.assertEqual(resp.status_code, 200)
        results = self._results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test issue")

    def test_status_open_filter(self):
        self._seed(external_id="x1", canonical_fingerprint="c1")
        self._seed(
            external_id="x2",
            canonical_fingerprint="c2",
            status=AutoIssue.STATUS_RESOLVED,
        )
        self.client.force_authenticate(self.viewer)
        resp = self.client.get("/api/auto-issues/?status=open")
        self.assertEqual(len(self._results(resp)), 1)
        resp = self.client.get("/api/auto-issues/?status=resolved")
        self.assertEqual(len(self._results(resp)), 1)

    def test_source_filter(self):
        self._seed(
            external_id="x1", canonical_fingerprint="c1",
            source=AutoIssue.SOURCE_GLITCHTIP,
        )
        self._seed(
            external_id="x2", canonical_fingerprint="c2",
            source=AutoIssue.SOURCE_PYROSCOPE,
        )
        self.client.force_authenticate(self.viewer)
        resp = self.client.get("/api/auto-issues/?source=pyroscope")
        results = self._results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "pyroscope")

    def test_arbitrary_status_filter_matches_exact_status(self):
        # views.py line 44: a status param that is neither "open" nor
        # "resolved" falls through to an exact `status=<param>` filter.
        self._seed(external_id="x1", canonical_fingerprint="c1")
        self._seed(
            external_id="x2",
            canonical_fingerprint="c2",
            status=AutoIssue.STATUS_PICKED,
        )
        self.client.force_authenticate(self.viewer)
        resp = self.client.get(
            f"/api/auto-issues/?status={AutoIssue.STATUS_PICKED}"
        )
        results = self._results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], AutoIssue.STATUS_PICKED)

    def test_category_filter_matches_category_key(self):
        # views.py line 50: a category param filters on the related
        # category's `key`, so only rows in that category come back.
        # Use test-specific keys via get_or_create so the pre-seeded
        # taxonomy (which already owns keys like "security") never collides.
        wanted, _ = AutoIssueCategory.objects.get_or_create(
            key="views-test-wanted", defaults={"label": "Views Test Wanted"}
        )
        other, _ = AutoIssueCategory.objects.get_or_create(
            key="views-test-other", defaults={"label": "Views Test Other"}
        )
        self._seed(external_id="x1", canonical_fingerprint="c1", category=wanted)
        self._seed(external_id="x2", canonical_fingerprint="c2", category=other)
        self.client.force_authenticate(self.viewer)
        resp = self.client.get("/api/auto-issues/?category=views-test-wanted")
        results = self._results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["external_id"], "x1")

    def test_resync_requires_admin(self):
        self.client.force_authenticate(self.viewer)
        resp = self.client.post("/api/auto-issues/resync/")
        self.assertEqual(resp.status_code, 403)

    def test_resync_returns_picker_results_for_admin(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/auto-issues/resync/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("glitchtip_sync", body)
        self.assertIn("glitchtip_picker", body)
        self.assertIn("internal_picker", body)
        self.assertIn("pyroscope_picker", body)
        self.assertIn("open_count", body)

    def test_flush_cache_requires_admin(self):
        self.client.force_authenticate(self.viewer)
        resp = self.client.post("/api/auto-issues/flush-cache/")
        self.assertEqual(resp.status_code, 403)

    def test_flush_cache_returns_count_for_admin(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/auto-issues/flush-cache/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("flushed_rows", resp.json())

    def test_detail_includes_lessons_learned(self):
        row = self._seed(
            status=AutoIssue.STATUS_RESOLVED,
            lessons_learned="Trap: ...\nFix: ...",
        )
        self.client.force_authenticate(self.viewer)
        resp = self.client.get(f"/api/auto-issues/{row.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["lessons_learned"], "Trap: ...\nFix: ...")

    def test_ingest_observability_accepts_anonymous_post(self):
        # The endpoint is AllowAny: an unauthenticated client can POST and
        # the view answers 200 {"status": "ok"} without touching the DB.
        resp = self.client.post(
            "/api/auto-issues/ingest-observability/",
            {"event": "alert", "value": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_ingest_observability_accepts_empty_body(self):
        # No payload at all is still accepted silently — Grafana/webhook
        # senders that POST nothing must not get a 4xx.
        resp = self.client.post("/api/auto-issues/ingest-observability/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_ingest_observability_rejects_get(self):
        # Only POST is routed; a GET to the action must 405, proving the
        # method allowlist on the new action is wired correctly.
        resp = self.client.get("/api/auto-issues/ingest-observability/")
        self.assertEqual(resp.status_code, 405)
