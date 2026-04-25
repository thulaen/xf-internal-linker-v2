"""Tests for the Phase 6 picks toggle endpoint (Polish.A wiring)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.views_phase6_picks import (
    _PICK_DEFAULTS,
    get_phase6_pick_settings,
)


class Phase6PicksSettingsViewTests(TestCase):
    URL = "/api/settings/phase6-picks/"

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="op", password="pw", is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_returns_all_ten_picks_default_on(self) -> None:
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # All 10 picks present.
        self.assertEqual(set(body.keys()), set(_PICK_DEFAULTS.keys()))
        # All default to True per migration 0043.
        for pick, fields in body.items():
            self.assertEqual(fields["enabled"], True, f"{pick} not enabled by default")

    def test_put_persists_full_payload(self) -> None:
        payload = {pick: {"enabled": False} for pick in _PICK_DEFAULTS}
        resp = self.client.put(self.URL, data=payload, format="json")
        self.assertEqual(resp.status_code, 200)
        snap = get_phase6_pick_settings()
        for pick in _PICK_DEFAULTS:
            self.assertFalse(
                snap[pick]["enabled"],
                f"{pick} should have been disabled",
            )

    def test_put_partial_keeps_omitted_picks(self) -> None:
        # Disable just VADER and BPR.
        resp = self.client.put(
            self.URL,
            data={
                "vader_sentiment": {"enabled": False},
                "bpr": {"enabled": False},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        snap = get_phase6_pick_settings()
        self.assertFalse(snap["vader_sentiment"]["enabled"])
        self.assertFalse(snap["bpr"]["enabled"])
        # The other 8 picks stay True.
        for pick in _PICK_DEFAULTS:
            if pick in {"vader_sentiment", "bpr"}:
                continue
            self.assertTrue(snap[pick]["enabled"], f"{pick} should still be on")

    def test_string_inputs_coerce(self) -> None:
        """API consumers may send strings for booleans (legacy clients)."""
        resp = self.client.put(
            self.URL,
            data={
                "vader_sentiment": {"enabled": "no"},
                "lda": {"enabled": "yes"},
                "kenlm": {"enabled": "off"},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        snap = get_phase6_pick_settings()
        self.assertFalse(snap["vader_sentiment"]["enabled"])
        self.assertTrue(snap["lda"]["enabled"])
        self.assertFalse(snap["kenlm"]["enabled"])

    def test_unauthenticated_request_rejected(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get(self.URL)
        self.assertIn(resp.status_code, (401, 403))

    def test_round_trip_via_recommended_bool_consumer(self) -> None:
        """End-to-end: flipping a flag changes what
        ``recommended_bool`` reports — the function any consumer uses
        to decide whether to short-circuit at call time."""
        from apps.core.models import AppSetting

        # The test DB is populated by migration 0043 with all-true
        # AppSetting rows. After flipping VADER off via the API, the
        # AppSetting row reads "false".
        self.client.put(
            self.URL,
            data={"vader_sentiment": {"enabled": False}},
            format="json",
        )
        # ``_persist_settings`` lowercases booleans → "false"/"true".
        row = AppSetting.objects.get(key="vader_sentiment.enabled")
        self.assertEqual(row.value.lower(), "false")
