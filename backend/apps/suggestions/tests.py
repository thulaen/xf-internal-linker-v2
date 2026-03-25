from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.core.models import AppSetting
from apps.content.models import ContentItem, Post, ScopeItem, Sentence, SiloGroup
from apps.pipeline.services.algorithm_versions import PHRASE_MATCHING_VERSION, WEIGHTED_AUTHORITY_VERSION
from apps.graph.models import LinkFreshnessEdge
from apps.suggestions.models import PipelineRun, Suggestion


class SuggestionSiloApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="reviewer", password="pass")
        self.client.force_authenticate(user=user)

        silo_a = SiloGroup.objects.create(name="Silo A", slug="silo-a")
        silo_b = SiloGroup.objects.create(name="Silo B", slug="silo-b")
        scope_a = ScopeItem.objects.create(scope_id=1, scope_type="node", title="A", silo_group=silo_a)
        scope_a_host = ScopeItem.objects.create(scope_id=2, scope_type="node", title="A Host", silo_group=silo_a)
        scope_b = ScopeItem.objects.create(scope_id=3, scope_type="node", title="B", silo_group=silo_b)
        scope_unassigned = ScopeItem.objects.create(scope_id=4, scope_type="node", title="Loose")

        dest_same = ContentItem.objects.create(content_id=10, content_type="thread", title="Dest Same", scope=scope_a)
        host_same = ContentItem.objects.create(content_id=11, content_type="thread", title="Host Same", scope=scope_a_host)
        host_cross = ContentItem.objects.create(content_id=12, content_type="thread", title="Host Cross", scope=scope_b)
        host_unassigned = ContentItem.objects.create(content_id=13, content_type="thread", title="Host Loose", scope=scope_unassigned)
        post_same = Post.objects.create(content_item=host_same, raw_bbcode="same", clean_text="same")
        post_cross = Post.objects.create(content_item=host_cross, raw_bbcode="cross", clean_text="cross")
        post_unassigned = Post.objects.create(content_item=host_unassigned, raw_bbcode="loose", clean_text="loose")

        sentence_same = Sentence.objects.create(
            content_item=host_same,
            post=post_same,
            text="Sentence same",
            position=0,
            char_count=12,
            start_char=0,
            end_char=12,
            word_position=1,
        )
        sentence_cross = Sentence.objects.create(
            content_item=host_cross,
            post=post_cross,
            text="Sentence cross",
            position=0,
            char_count=14,
            start_char=0,
            end_char=14,
            word_position=1,
        )
        sentence_unassigned = Sentence.objects.create(
            content_item=host_unassigned,
            post=post_unassigned,
            text="Sentence loose",
            position=0,
            char_count=14,
            start_char=0,
            end_char=14,
            word_position=1,
        )

        Suggestion.objects.create(
            destination=dest_same,
            destination_title=dest_same.title,
            host=host_same,
            host_sentence=sentence_same,
            host_sentence_text=sentence_same.text,
            anchor_phrase="same",
            status="pending",
        )
        Suggestion.objects.create(
            destination=dest_same,
            destination_title=dest_same.title,
            host=host_cross,
            host_sentence=sentence_cross,
            host_sentence_text=sentence_cross.text,
            anchor_phrase="cross",
            status="pending",
        )
        Suggestion.objects.create(
            destination=dest_same,
            destination_title=dest_same.title,
            host=host_unassigned,
            host_sentence=sentence_unassigned,
            host_sentence_text=sentence_unassigned.text,
            anchor_phrase="loose",
            status="pending",
        )

    def test_same_silo_filter_returns_only_same_silo_suggestions(self):
        response = self.client.get("/api/suggestions/?same_silo=true")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        suggestion = payload["results"][0]
        self.assertTrue(suggestion["same_silo"])
        self.assertEqual(suggestion["destination_silo_group_name"], "Silo A")
        self.assertEqual(suggestion["host_silo_group_name"], "Silo A")

    def test_suggestion_list_exposes_source_labels_for_cross_source_review(self):
        response = self.client.get("/api/suggestions/")

        self.assertEqual(response.status_code, 200)
        suggestion = response.json()["results"][0]
        self.assertEqual(suggestion["destination_source_label"], "XenForo")
        self.assertEqual(suggestion["host_source_label"], "XenForo")
        self.assertEqual(suggestion["destination_content_type"], "thread")
        self.assertEqual(suggestion["host_content_type"], "thread")

    def test_suggestion_detail_exposes_march_2026_pagerank_field(self):
        suggestion = Suggestion.objects.first()
        suggestion.score_march_2026_pagerank = 0.35
        suggestion.score_link_freshness = 0.72
        suggestion.score_phrase_relevance = 0.83
        suggestion.phrase_match_diagnostics = {
            "score_phrase_relevance": 0.83,
            "phrase_match_state": "computed_exact_title",
            "selected_anchor_text": "same",
            "selected_anchor_start": 0,
            "selected_anchor_end": 4,
            "selected_match_type": "exact",
            "selected_phrase_source": "title",
            "selected_token_count": 1,
            "context_window_tokens": 8,
            "context_corroborating_hits": 1,
            "destination_phrase_count": 6,
        }
        suggestion.save(
            update_fields=[
                "score_march_2026_pagerank",
                "score_link_freshness",
                "score_phrase_relevance",
                "phrase_match_diagnostics",
                "updated_at",
            ]
        )
        LinkFreshnessEdge.objects.create(
            from_content_item=suggestion.host,
            to_content_item=suggestion.destination,
            first_seen_at=suggestion.created_at,
            last_seen_at=suggestion.created_at,
            is_active=True,
        )

        response = self.client.get(f"/api/suggestions/{suggestion.suggestion_id}/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["score_march_2026_pagerank"], 0.35)
        self.assertEqual(payload["score_link_freshness"], 0.72)
        self.assertEqual(payload["score_phrase_relevance"], 0.83)
        self.assertIn("phrase_match_diagnostics", payload)
        self.assertEqual(payload["phrase_match_diagnostics"]["phrase_match_state"], "computed_exact_title")
        self.assertIn("link_freshness_diagnostics", payload)
        self.assertEqual(payload["link_freshness_diagnostics"]["link_freshness_score"], 0.5)


class PipelineRunWeightedSnapshotTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="pipeline-user", password="pass")
        self.client.force_authenticate(user=user)

    @patch("apps.pipeline.tasks.run_pipeline.delay")
    def test_start_pipeline_persists_weighted_authority_snapshot(self, delay_mock):
        AppSetting.objects.create(
            key="weighted_authority.ranking_weight",
            value="0.2",
            value_type="float",
            category="ml",
            description="Ranking weight",
        )
        AppSetting.objects.create(
            key="weighted_authority.position_bias",
            value="0.4",
            value_type="float",
            category="ml",
            description="Position bias",
        )
        AppSetting.objects.create(
            key="phrase_matching.context_window_tokens",
            value="10",
            value_type="int",
            category="anchor",
            description="Context window",
        )

        response = self.client.post("/api/pipeline-runs/start/", {"rerun_mode": "skip_pending"}, format="json")

        self.assertEqual(response.status_code, 201)
        run = PipelineRun.objects.get(run_id=response.json()["run_id"])
        self.assertIn("weighted_authority", run.config_snapshot)
        self.assertEqual(run.config_snapshot["weighted_authority"]["ranking_weight"], 0.2)
        self.assertEqual(run.config_snapshot["weighted_authority"]["position_bias"], 0.4)
        self.assertIn("algorithm_versions", run.config_snapshot)
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["weighted_authority"],
            WEIGHTED_AUTHORITY_VERSION,
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["weighted_authority"]["version_date"],
            "2026-03-25",
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["weighted_authority"]["version_month"],
            "March",
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["weighted_authority"]["version_year"],
            2026,
        )
        self.assertIn("phrase_matching", run.config_snapshot)
        self.assertEqual(run.config_snapshot["phrase_matching"]["context_window_tokens"], 10)
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["phrase_matching"],
            PHRASE_MATCHING_VERSION,
        )
        delay_mock.assert_called_once()
