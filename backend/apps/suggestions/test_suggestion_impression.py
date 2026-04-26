"""Tests for the ``SuggestionImpression`` model + bulk-log endpoint.

Both pieces are the producer-side input that picks #33 (IPS Position
Bias) and #34 (Cascade Click Model) read from. The model is purely
additive — until the frontend hook starts POSTing rows, this table
is empty and the producer scheduled jobs no-op cleanly.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.content.models import ContentItem, Post, ScopeItem, Sentence
from apps.suggestions.models import (
    PipelineRun,
    Suggestion,
    SuggestionImpression,
)


class _Fixture:
    @staticmethod
    def make() -> dict:
        scope = ScopeItem.objects.create(scope_id=33, scope_type="node", title="impr")
        host = ContentItem.objects.create(
            content_id=3300, content_type="thread", title="host", scope=scope
        )
        host_post = Post.objects.create(
            content_item=host, raw_bbcode="x", clean_text="x"
        )
        host_sentence = Sentence.objects.create(
            content_item=host,
            post=host_post,
            text="A host sentence.",
            position=0,
            char_count=18,
            start_char=0,
            end_char=18,
            word_position=0,
        )
        dest = ContentItem.objects.create(
            content_id=3301, content_type="thread", title="dest", scope=scope
        )
        run = PipelineRun.objects.create()
        suggestion = Suggestion.objects.create(
            pipeline_run=run,
            destination=dest,
            host=host,
            host_sentence=host_sentence,
            destination_title="dest",
            host_sentence_text="A host sentence.",
            anchor_phrase="anchor",
            anchor_start=0,
            anchor_end=6,
            anchor_confidence="strong",
            score_final=0.5,
            status="pending",
        )
        return {"scope": scope, "host": host, "dest": dest, "suggestion": suggestion}


class SuggestionImpressionModelTests(TestCase):
    def test_create_basic_impression(self) -> None:
        f = _Fixture.make()
        impr = SuggestionImpression.objects.create(
            suggestion=f["suggestion"],
            position=3,
            clicked=False,
        )
        self.assertEqual(impr.position, 3)
        self.assertFalse(impr.clicked)
        self.assertIsNone(impr.dwell_ms)
        self.assertIsNotNone(impr.impressed_at)

    def test_dwell_ms_optional(self) -> None:
        """``dwell_ms`` is null until the frontend's viewport timer reports."""
        f = _Fixture.make()
        impr = SuggestionImpression.objects.create(
            suggestion=f["suggestion"],
            position=0,
            clicked=True,
            dwell_ms=2500,
        )
        self.assertEqual(impr.dwell_ms, 2500)

    def test_string_repr(self) -> None:
        f = _Fixture.make()
        impr = SuggestionImpression.objects.create(
            suggestion=f["suggestion"], position=7, clicked=True
        )
        self.assertIn("pos=7", str(impr))
        self.assertIn(str(f["suggestion"].pk), str(impr))


class SuggestionImpressionEndpointTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(
            username="op", password="pw", is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_post_empty_array_returns_zero(self) -> None:
        resp = self.client.post("/api/suggestions/impressions/", [], format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["written"], 0)

    def test_post_invalid_payload_400(self) -> None:
        resp = self.client.post(
            "/api/suggestions/impressions/", {"not_a_list": True}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_writes_valid_rows(self) -> None:
        f = _Fixture.make()
        resp = self.client.post(
            "/api/suggestions/impressions/",
            [
                {
                    "suggestion_id": f["suggestion"].pk,
                    "position": 0,
                    "clicked": False,
                },
                {
                    "suggestion_id": f["suggestion"].pk,
                    "position": 1,
                    "clicked": True,
                    "dwell_ms": 2000,
                },
            ],
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["written"], 2)
        self.assertEqual(SuggestionImpression.objects.count(), 2)

    def test_post_skips_unknown_suggestion_ids(self) -> None:
        """Stale rows in the operator's queue don't reject the whole batch."""
        f = _Fixture.make()
        resp = self.client.post(
            "/api/suggestions/impressions/",
            [
                {
                    "suggestion_id": f["suggestion"].pk,
                    "position": 0,
                    "clicked": False,
                },
                {"suggestion_id": 9_999_999, "position": 1, "clicked": False},
            ],
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        # Only the valid row landed.
        self.assertEqual(resp.json()["written"], 1)
        self.assertEqual(SuggestionImpression.objects.count(), 1)

    def test_post_skips_malformed_rows(self) -> None:
        """Rows missing required fields are silently dropped."""
        f = _Fixture.make()
        resp = self.client.post(
            "/api/suggestions/impressions/",
            [
                {"suggestion_id": f["suggestion"].pk, "position": 0},
                # Missing position.
                {"suggestion_id": f["suggestion"].pk},
                # Missing suggestion_id.
                {"position": 5},
                # Wrong type for position.
                {"suggestion_id": f["suggestion"].pk, "position": "abc"},
            ],
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["written"], 1)

    def test_post_requires_authentication(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.post("/api/suggestions/impressions/", [], format="json")
        # DRF returns 403 Forbidden (not 401) when no credentials are
        # provided and the view's permission class is IsAuthenticated.
        # That's the standard DRF behaviour — see
        # https://www.django-rest-framework.org/api-guide/authentication/#unauthorized-and-forbidden-responses
        self.assertIn(resp.status_code, (401, 403))
