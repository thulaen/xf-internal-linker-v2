"""Tests for the NDCG eval read endpoint (Polish.B)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class NdcgEvalViewTests(TestCase):
    URL = "/api/system/status/ndcg-eval/"

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="op", password="pw", is_staff=True
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_cold_start_returns_unavailable(self) -> None:
        """No persisted result → endpoint says eval-not-run-yet."""
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["available"])
        self.assertIn("not run yet", body["message"].lower())

    def test_unauthenticated_request_rejected(self) -> None:
        self.client.force_authenticate(user=None)
        resp = self.client.get(self.URL)
        self.assertIn(resp.status_code, (401, 403))

    def test_returns_full_shape_after_eval_runs(self) -> None:
        from apps.content.models import (
            ContentItem,
            Post,
            ScopeItem,
            Sentence,
        )
        from apps.pipeline.services.ndcg_eval import (
            SANDERSON_BASIC_FLOOR,
            evaluate_and_persist,
        )
        from apps.suggestions.models import PipelineRun, Suggestion

        scope = ScopeItem.objects.create(
            scope_id=88, scope_type="node", title="ndcg-view"
        )
        host_ci = ContentItem.objects.create(
            content_id=8800,
            content_type="thread",
            title="host",
            scope=scope,
        )
        host_post = Post.objects.create(
            content_item=host_ci, raw_bbcode="x", clean_text="x"
        )
        host_sentence = Sentence.objects.create(
            content_item=host_ci,
            post=host_post,
            text="A host sentence.",
            position=0,
            char_count=18,
            start_char=0,
            end_char=18,
            word_position=0,
        )
        dest_ci = ContentItem.objects.create(
            content_id=8801,
            content_type="thread",
            title="dest",
            scope=scope,
        )
        run = PipelineRun.objects.create()
        # Seed enough reviewed Suggestions to clear the basic floor.
        rows = []
        for i in range(SANDERSON_BASIC_FLOOR + 5):
            rows.append(
                Suggestion(
                    pipeline_run=run,
                    destination=dest_ci,
                    host=host_ci,
                    host_sentence=host_sentence,
                    destination_title=f"dest-{i}",
                    host_sentence_text="A host sentence.",
                    anchor_phrase="anchor",
                    anchor_start=0,
                    anchor_end=6,
                    anchor_confidence="strong",
                    score_final=(SANDERSON_BASIC_FLOOR + 5 - i) / float(
                        SANDERSON_BASIC_FLOOR + 5
                    ),
                    status="approved" if i < (SANDERSON_BASIC_FLOOR // 2) else "rejected",
                    candidate_origin="semantic",
                )
            )
        Suggestion.objects.bulk_create(rows)
        evaluate_and_persist()

        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["available"])
        self.assertTrue(body["sufficient_data"])
        self.assertEqual(body["k"], 10)
        self.assertGreaterEqual(body["sample_size"], SANDERSON_BASIC_FLOOR)
        # Confidence band brackets the point estimate.
        self.assertLessEqual(body["confidence_lower"], body["ndcg"] + 1e-6)
        self.assertGreaterEqual(body["confidence_upper"], body["ndcg"] - 1e-6)
        self.assertIn("breakdown_by_candidate_origin", body)
