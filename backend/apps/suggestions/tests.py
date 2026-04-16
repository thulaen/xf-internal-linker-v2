from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.core.models import AppSetting
from apps.content.models import ContentItem, Post, ScopeItem, Sentence, SiloGroup
from apps.pipeline.services.algorithm_versions import (
    FIELD_AWARE_RELEVANCE_VERSION,
    LEARNED_ANCHOR_VERSION,
    PHRASE_MATCHING_VERSION,
    RARE_TERM_PROPAGATION_VERSION,
    WEIGHTED_AUTHORITY_VERSION,
)
from apps.graph.models import LinkFreshnessEdge
from apps.suggestions.models import HoldoutQuery, PipelineRun, Suggestion
from apps.suggestions.services.meta_rotation_scheduler import (
    _evaluate_meta_on_holdout,
    _should_promote,
    run_meta_tournament,
)
from apps.suggestions.services.meta_slot_registry import (
    META_SLOT_REGISTRY,
    MetaSlotConfig,
)


class SuggestionSiloApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="reviewer", password="pass"
        )
        self.client.force_authenticate(user=user)

        silo_a = SiloGroup.objects.create(name="Silo A", slug="silo-a")
        silo_b = SiloGroup.objects.create(name="Silo B", slug="silo-b")
        scope_a = ScopeItem.objects.create(
            scope_id=1, scope_type="node", title="A", silo_group=silo_a
        )
        scope_a_host = ScopeItem.objects.create(
            scope_id=2, scope_type="node", title="A Host", silo_group=silo_a
        )
        scope_b = ScopeItem.objects.create(
            scope_id=3, scope_type="node", title="B", silo_group=silo_b
        )
        scope_unassigned = ScopeItem.objects.create(
            scope_id=4, scope_type="node", title="Loose"
        )

        dest_same = ContentItem.objects.create(
            content_id=10,
            content_type="thread",
            title="Dest Same",
            url="https://example.test/dest-same",
            scope=scope_a,
        )
        host_same = ContentItem.objects.create(
            content_id=11, content_type="thread", title="Host Same", scope=scope_a_host
        )
        host_cross = ContentItem.objects.create(
            content_id=12, content_type="thread", title="Host Cross", scope=scope_b
        )
        host_unassigned = ContentItem.objects.create(
            content_id=13,
            content_type="thread",
            title="Host Loose",
            scope=scope_unassigned,
        )
        post_same = Post.objects.create(
            content_item=host_same, raw_bbcode="same", clean_text="same"
        )
        post_cross = Post.objects.create(
            content_item=host_cross, raw_bbcode="cross", clean_text="cross"
        )
        post_unassigned = Post.objects.create(
            content_item=host_unassigned, raw_bbcode="loose", clean_text="loose"
        )

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
        suggestion.score_learned_anchor_corroboration = 0.91
        suggestion.score_rare_term_propagation = 0.88
        suggestion.score_field_aware_relevance = 0.86
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
        suggestion.learned_anchor_diagnostics = {
            "score_learned_anchor_corroboration": 0.91,
            "learned_anchor_state": "exact_variant_match",
            "candidate_anchor_text": "same",
            "candidate_anchor_normalized": "same",
            "matched_family_canonical": "Same",
            "matched_variant_display": "Same",
            "family_support_share": 1.0,
            "variant_support_share": 1.0,
            "supporting_source_count": 2,
            "usable_inbound_anchor_sources": 2,
            "learned_family_count": 1,
            "top_learned_families": [
                {
                    "canonical_anchor": "Same",
                    "support_share": 1.0,
                    "supporting_source_count": 2,
                    "alternate_variants": [],
                }
            ],
            "host_contains_canonical_variant": False,
            "recommended_canonical_anchor": "Same",
        }
        suggestion.rare_term_diagnostics = {
            "score_rare_term_propagation": 0.88,
            "rare_term_state": "computed_match",
            "original_destination_terms": ["guide", "internal", "linking"],
            "propagated_term_candidates": [
                {
                    "term": "xenforo",
                    "document_frequency": 2,
                    "supporting_related_pages": 2,
                    "supporting_relationship_weights": [1.0, 0.75],
                    "average_relationship_weight": 0.875,
                    "term_evidence": 0.76,
                }
            ],
            "matched_propagated_terms": [
                {
                    "term": "xenforo",
                    "document_frequency": 2,
                    "supporting_related_pages": 2,
                    "supporting_relationship_weights": [1.0, 0.75],
                    "average_relationship_weight": 0.875,
                    "term_evidence": 0.76,
                }
            ],
            "top_propagated_terms": [
                {
                    "term": "xenforo",
                    "document_frequency": 2,
                    "supporting_related_pages": 2,
                    "supporting_relationship_weights": [1.0, 0.75],
                    "average_relationship_weight": 0.875,
                    "term_evidence": 0.76,
                }
            ],
            "eligible_related_page_count": 2,
            "related_page_summary": [
                {
                    "content_id": 201,
                    "relationship_tier": "same_scope",
                    "shared_original_token_count": 2,
                }
            ],
            "max_document_frequency": 3,
            "minimum_supporting_related_pages": 2,
        }
        suggestion.field_aware_diagnostics = {
            "score_field_aware_relevance": 0.86,
            "field_aware_state": "computed_match",
            "field_weights": {
                "title": 0.4,
                "body": 0.3,
                "scope": 0.15,
                "learned_anchor": 0.15,
            },
            "field_lengths": {
                "title": 2,
                "body": 4,
                "scope": 1,
                "learned_anchor": 1,
            },
            "matched_field_count": 3,
            "field_scores": {
                "title": {"score": 0.8, "matched_terms": [{"token": "same"}]},
                "body": {"score": 0.7, "matched_terms": [{"token": "guide"}]},
                "scope": {"score": 0.6, "matched_terms": [{"token": "a"}]},
                "learned_anchor": {"score": 0.0, "matched_terms": []},
            },
        }
        suggestion.save(
            update_fields=[
                "score_march_2026_pagerank",
                "score_link_freshness",
                "score_phrase_relevance",
                "score_learned_anchor_corroboration",
                "score_rare_term_propagation",
                "score_field_aware_relevance",
                "phrase_match_diagnostics",
                "learned_anchor_diagnostics",
                "rare_term_diagnostics",
                "field_aware_diagnostics",
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
        self.assertEqual(payload["score_learned_anchor_corroboration"], 0.91)
        self.assertEqual(payload["score_rare_term_propagation"], 0.88)
        self.assertEqual(payload["score_field_aware_relevance"], 0.86)
        self.assertIn("phrase_match_diagnostics", payload)
        self.assertIn("learned_anchor_diagnostics", payload)
        self.assertIn("rare_term_diagnostics", payload)
        self.assertIn("field_aware_diagnostics", payload)
        self.assertEqual(
            payload["phrase_match_diagnostics"]["phrase_match_state"],
            "computed_exact_title",
        )
        self.assertEqual(
            payload["learned_anchor_diagnostics"]["learned_anchor_state"],
            "exact_variant_match",
        )
        self.assertEqual(
            payload["rare_term_diagnostics"]["rare_term_state"], "computed_match"
        )
        self.assertEqual(
            payload["field_aware_diagnostics"]["field_aware_state"], "computed_match"
        )
        self.assertIn("link_freshness_diagnostics", payload)
        self.assertEqual(
            payload["link_freshness_diagnostics"]["link_freshness_score"], 0.5
        )
        self.assertIn("telemetry_instrumentation", payload)
        self.assertEqual(payload["telemetry_instrumentation"]["status"], "instrumented")
        self.assertEqual(
            payload["telemetry_instrumentation"]["event_schema"], "fr016_v1"
        )
        self.assertIn(
            "data-xfil-suggestion-id",
            payload["telemetry_instrumentation"]["attributes"],
        )
        self.assertIn(
            str(suggestion.suggestion_id),
            payload["telemetry_instrumentation"]["instrumented_markup"],
        )


class PipelineRunWeightedSnapshotTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="pipeline-user", password="pass"
        )
        self.client.force_authenticate(user=user)

    @patch("apps.pipeline.tasks.dispatch_pipeline_run")
    def test_start_pipeline_persists_weighted_authority_snapshot(
        self, dispatch_pipeline_mock
    ):
        AppSetting.objects.update_or_create(
            key="weighted_authority.ranking_weight",
            defaults={
                "value": "0.2",
                "value_type": "float",
                "category": "ml",
                "description": "Ranking weight",
            },
        )
        AppSetting.objects.update_or_create(
            key="weighted_authority.position_bias",
            defaults={
                "value": "0.4",
                "value_type": "float",
                "category": "ml",
                "description": "Position bias",
            },
        )
        AppSetting.objects.update_or_create(
            key="phrase_matching.context_window_tokens",
            defaults={
                "value": "10",
                "value_type": "int",
                "category": "anchor",
                "description": "Context window",
            },
        )
        AppSetting.objects.update_or_create(
            key="learned_anchor.minimum_anchor_sources",
            defaults={
                "value": "4",
                "value_type": "int",
                "category": "anchor",
                "description": "Minimum anchor sources",
            },
        )
        AppSetting.objects.update_or_create(
            key="rare_term_propagation.max_document_frequency",
            defaults={
                "value": "5",
                "value_type": "int",
                "category": "ml",
                "description": "Rare-term max document frequency",
            },
        )
        AppSetting.objects.update_or_create(
            key="field_aware_relevance.title_field_weight",
            defaults={
                "value": "0.5",
                "value_type": "float",
                "category": "ml",
                "description": "Field-aware title weight",
            },
        )
        AppSetting.objects.update_or_create(
            key="field_aware_relevance.body_field_weight",
            defaults={
                "value": "0.2",
                "value_type": "float",
                "category": "ml",
                "description": "Field-aware body weight",
            },
        )

        response = self.client.post(
            "/api/pipeline-runs/start/", {"rerun_mode": "skip_pending"}, format="json"
        )

        self.assertEqual(response.status_code, 201)
        run = PipelineRun.objects.get(run_id=response.json()["run_id"])
        self.assertIn("weighted_authority", run.config_snapshot)
        self.assertEqual(
            run.config_snapshot["weighted_authority"]["ranking_weight"], 0.2
        )
        self.assertEqual(
            run.config_snapshot["weighted_authority"]["position_bias"], 0.4
        )
        self.assertIn("algorithm_versions", run.config_snapshot)
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["weighted_authority"],
            WEIGHTED_AUTHORITY_VERSION,
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["weighted_authority"][
                "version_date"
            ],
            "2026-03-25",
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["weighted_authority"][
                "version_month"
            ],
            "March",
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["weighted_authority"][
                "version_year"
            ],
            2026,
        )
        self.assertIn("phrase_matching", run.config_snapshot)
        self.assertEqual(
            run.config_snapshot["phrase_matching"]["context_window_tokens"], 10
        )
        self.assertIn("learned_anchor", run.config_snapshot)
        self.assertEqual(
            run.config_snapshot["learned_anchor"]["minimum_anchor_sources"], 4
        )
        self.assertIn("rare_term_propagation", run.config_snapshot)
        self.assertEqual(
            run.config_snapshot["rare_term_propagation"]["max_document_frequency"], 5
        )
        self.assertIn("field_aware_relevance", run.config_snapshot)
        self.assertEqual(
            run.config_snapshot["field_aware_relevance"]["title_field_weight"], 0.5
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["phrase_matching"],
            PHRASE_MATCHING_VERSION,
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["learned_anchor"],
            LEARNED_ANCHOR_VERSION,
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["rare_term_propagation"],
            RARE_TERM_PROPAGATION_VERSION,
        )
        self.assertEqual(
            run.config_snapshot["algorithm_versions"]["field_aware_relevance"],
            FIELD_AWARE_RELEVANCE_VERSION,
        )
        dispatch_pipeline_mock.assert_called_once()


class SuggestionBatchActionApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="batch-reviewer", password="pass"
        )
        self.client.force_authenticate(user=user)

        self.scope = ScopeItem.objects.create(
            scope_id=20, scope_type="node", title="Forum"
        )
        self.destination = ContentItem.objects.create(
            content_id=200, content_type="thread", title="Destination", scope=self.scope
        )

        self.pending = self._suggestion(
            content_id=201, title="Pending Host", status="pending"
        )
        self.approved_reviewed_at = timezone.now()
        self.approved = self._suggestion(
            content_id=202,
            title="Approved Host",
            status="approved",
            reviewed_at=self.approved_reviewed_at,
        )
        self.rejected_reviewed_at = timezone.now()
        self.rejected = self._suggestion(
            content_id=203,
            title="Rejected Host",
            status="rejected",
            reviewed_at=self.rejected_reviewed_at,
            rejection_reason="duplicate",
        )

    def _suggestion(
        self,
        *,
        content_id: int,
        title: str,
        status: str,
        reviewed_at=None,
        rejection_reason: str = "",
    ) -> Suggestion:
        host = ContentItem.objects.create(
            content_id=content_id, content_type="thread", title=title, scope=self.scope
        )
        post = Post.objects.create(
            content_item=host, raw_bbcode=title, clean_text=title
        )
        sentence = Sentence.objects.create(
            content_item=host,
            post=post,
            text=f"{title} sentence",
            position=0,
            char_count=len(f"{title} sentence"),
            start_char=0,
            end_char=len(f"{title} sentence"),
            word_position=1,
        )
        return Suggestion.objects.create(
            destination=self.destination,
            destination_title=self.destination.title,
            host=host,
            host_sentence=sentence,
            host_sentence_text=sentence.text,
            anchor_phrase="anchor",
            status=status,
            reviewed_at=reviewed_at,
            rejection_reason=rejection_reason,
        )

    def test_batch_approve_only_updates_pending_suggestions_and_keeps_response_shape(
        self,
    ):
        response = self.client.post(
            "/api/suggestions/batch_action/",
            {
                "action": "approve",
                "ids": [
                    str(self.pending.suggestion_id),
                    str(self.approved.suggestion_id),
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"updated": 1})

        self.pending.refresh_from_db()
        self.approved.refresh_from_db()

        self.assertEqual(self.pending.status, "approved")
        self.assertIsNotNone(self.pending.reviewed_at)
        self.assertEqual(self.approved.status, "approved")
        self.assertEqual(self.approved.reviewed_at, self.approved_reviewed_at)

    def test_batch_reject_only_updates_pending_suggestions_and_leaves_non_pending_untouched(
        self,
    ):
        response = self.client.post(
            "/api/suggestions/batch_action/",
            {
                "action": "reject",
                "ids": [
                    str(self.pending.suggestion_id),
                    str(self.rejected.suggestion_id),
                ],
                "rejection_reason": "wrong_context",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"updated": 1})

        self.pending.refresh_from_db()
        self.rejected.refresh_from_db()

        self.assertEqual(self.pending.status, "rejected")
        self.assertEqual(self.pending.rejection_reason, "wrong_context")
        self.assertIsNotNone(self.pending.reviewed_at)
        self.assertEqual(self.rejected.status, "rejected")
        self.assertEqual(self.rejected.reviewed_at, self.rejected_reviewed_at)
        self.assertEqual(self.rejected.rejection_reason, "duplicate")


# ---------------------------------------------------------------------------
# FR-225 Meta Rotation Scheduler Tests
# ---------------------------------------------------------------------------


def _make_holdout(
    host_id, stage_slot, algo_slug, window_start, per_suggestion_data, meets_min=True
):
    """Create a HoldoutQuery without needing real ContentItem or PipelineRun FKs."""
    return HoldoutQuery(
        host_id=host_id,
        stage_slot=stage_slot,
        algorithm_version_slug=algo_slug,
        pipeline_run=None,
        window_start=window_start,
        window_end=window_start + timedelta(days=29),
        window_days=30,
        impressions_ga4=100,
        impressions_matomo=95,
        meets_min_impressions=meets_min,
        sources_agree=True,
        suggestion_ids=[],
        per_suggestion_data=per_suggestion_data,
    )


def _grade_data(rank: int, grade: int, recency: float = 1.0, ips: float = 1.0) -> dict:
    return {
        "rank_position": rank,
        "ndcg_grade": grade,
        "impression_recency_weight": recency,
        "ips_weight": ips,
    }


class TestShouldPromote(TestCase):
    def test_promotes_when_delta_exceeds_threshold(self):
        assert (
            _should_promote("old", "new", ndcg_delta=0.015, threshold_pct=1.0) is True
        )

    def test_no_promote_when_delta_below_threshold(self):
        assert (
            _should_promote("old", "new", ndcg_delta=0.009, threshold_pct=1.0) is False
        )

    def test_no_promote_when_tie_same_meta(self):
        assert (
            _should_promote("lbfgs_b", "lbfgs_b", ndcg_delta=0.05, threshold_pct=1.0)
            is False
        )

    def test_no_promote_when_delta_exactly_below_threshold(self):
        assert (
            _should_promote("old", "new", ndcg_delta=0.0099, threshold_pct=1.0) is False
        )

    def test_promotes_at_exact_threshold(self):
        assert _should_promote("old", "new", ndcg_delta=0.01, threshold_pct=1.0) is True

    def test_no_promote_when_challenger_is_worse(self):
        assert (
            _should_promote("old", "new", ndcg_delta=-0.05, threshold_pct=1.0) is False
        )


class TestNdcgFormula(TestCase):
    def test_perfect_ranking_gives_ndcg_1(self):
        rows = [
            _make_holdout(
                host_id=1,
                stage_slot="test_slot",
                algo_slug="v1",
                window_start=date.today(),
                per_suggestion_data={
                    "s1": _grade_data(rank=1, grade=3),
                    "s2": _grade_data(rank=2, grade=2),
                    "s3": _grade_data(rank=3, grade=1),
                },
            )
        ]
        ndcg = _evaluate_meta_on_holdout("any_meta", rows)
        assert abs(ndcg - 1.0) < 1e-6, f"Expected 1.0, got {ndcg}"

    def test_reversed_ranking_gives_low_ndcg(self):
        rows = [
            _make_holdout(
                host_id=1,
                stage_slot="test_slot",
                algo_slug="v1",
                window_start=date.today(),
                per_suggestion_data={
                    "s1": _grade_data(rank=1, grade=0),
                    "s2": _grade_data(rank=2, grade=0),
                    "s3": _grade_data(rank=3, grade=3),
                },
            )
        ]
        ndcg = _evaluate_meta_on_holdout("any_meta", rows)
        assert ndcg < 0.6, f"Expected low NDCG for reversed ranking, got {ndcg}"

    def test_all_grade_zero_skipped(self):
        rows = [
            _make_holdout(
                host_id=1,
                stage_slot="test_slot",
                algo_slug="v1",
                window_start=date.today(),
                per_suggestion_data={
                    "s1": _grade_data(rank=1, grade=0),
                    "s2": _grade_data(rank=2, grade=0),
                },
            )
        ]
        ndcg = _evaluate_meta_on_holdout("any_meta", rows)
        assert ndcg == 0.0

    def test_empty_per_suggestion_data_skipped(self):
        rows = [
            _make_holdout(
                host_id=1,
                stage_slot="test_slot",
                algo_slug="v1",
                window_start=date.today(),
                per_suggestion_data={},
            )
        ]
        ndcg = _evaluate_meta_on_holdout("any_meta", rows)
        assert ndcg == 0.0

    def test_positions_beyond_10_ignored(self):
        rows = [
            _make_holdout(
                host_id=1,
                stage_slot="test_slot",
                algo_slug="v1",
                window_start=date.today(),
                per_suggestion_data={
                    "s1": _grade_data(rank=11, grade=3),
                    "s2": _grade_data(rank=1, grade=1),
                },
            )
        ]
        ndcg = _evaluate_meta_on_holdout("any_meta", rows)
        assert (
            ndcg < 1.0
        ), f"Expected NDCG < 1 when best item is beyond rank 10, got {ndcg}"
        assert ndcg > 0.0, "Expected NDCG > 0 when a grade-1 item is at rank 1"

    def test_recency_weight_scales_actual_dcg(self):
        rows_full = [
            _make_holdout(
                host_id=1,
                stage_slot="slot",
                algo_slug="v1",
                window_start=date.today(),
                per_suggestion_data={"s1": _grade_data(rank=1, grade=3, recency=1.0)},
            )
        ]
        rows_half = [
            _make_holdout(
                host_id=1,
                stage_slot="slot",
                algo_slug="v1",
                window_start=date.today(),
                per_suggestion_data={"s1": _grade_data(rank=1, grade=3, recency=0.5)},
            )
        ]
        ndcg_full = _evaluate_meta_on_holdout("any_meta", rows_full)
        ndcg_half = _evaluate_meta_on_holdout("any_meta", rows_half)
        assert abs(ndcg_full - 1.0) < 1e-6, f"Expected 1.0, got {ndcg_full}"
        assert abs(ndcg_half - 0.5) < 1e-6, f"Expected 0.5, got {ndcg_half}"


class TestRunMetaTournament(TestCase):
    def setUp(self):
        self._original_slot = META_SLOT_REGISTRY.get("second_order_optimizer")

    def tearDown(self):
        if self._original_slot is not None:
            META_SLOT_REGISTRY["second_order_optimizer"] = self._original_slot

    @patch(
        "apps.suggestions.services.meta_rotation_scheduler._is_rotation_enabled",
        return_value=False,
    )
    def test_skips_all_when_disabled(self, _mock):
        outcomes = run_meta_tournament()
        assert outcomes == []

    @patch(
        "apps.suggestions.services.meta_rotation_scheduler._is_rotation_enabled",
        return_value=True,
    )
    @patch("apps.suggestions.services.meta_rotation_scheduler._setting_int")
    def test_skips_slot_with_insufficient_holdout_rows(
        self, mock_setting, _mock_enabled
    ):
        mock_setting.side_effect = lambda key, default: (
            100 if key == "meta_rotation.min_holdout_queries" else default
        )
        outcomes = run_meta_tournament(slot_id="second_order_optimizer")
        assert len(outcomes) == 1
        assert outcomes[0].skipped is True
        assert "insufficient_evidence" in outcomes[0].skip_reason

    @patch(
        "apps.suggestions.services.meta_rotation_scheduler._is_rotation_enabled",
        return_value=True,
    )
    def test_pinned_slot_is_skipped(self, _mock_enabled):
        META_SLOT_REGISTRY["second_order_optimizer"].pinned = True
        outcomes = run_meta_tournament(slot_id="second_order_optimizer")
        assert outcomes[0].skipped is True
        assert outcomes[0].skip_reason == "operator_pinned"
        META_SLOT_REGISTRY["second_order_optimizer"].pinned = False

    @patch(
        "apps.suggestions.services.meta_rotation_scheduler._is_rotation_enabled",
        return_value=True,
    )
    def test_all_active_slot_returns_without_tournament(self, _mock_enabled):
        outcomes = run_meta_tournament(slot_id="feature_attribution")
        assert len(outcomes) == 1
        assert outcomes[0].skipped is False
        assert outcomes[0].winner == "all"
        assert outcomes[0].promoted is False

    @patch(
        "apps.suggestions.services.meta_rotation_scheduler._is_rotation_enabled",
        return_value=True,
    )
    @patch("apps.suggestions.services.meta_rotation_scheduler._setting_int")
    @patch("apps.suggestions.services.meta_rotation_scheduler._setting_float")
    @patch("apps.suggestions.services.meta_rotation_scheduler.HoldoutQuery")
    @patch("apps.suggestions.services.meta_rotation_scheduler.MetaTournamentResult")
    def test_promotes_meta_with_highest_ndcg(
        self, mock_result, mock_hq, mock_float, mock_int, _mock_enabled
    ):
        mock_int.side_effect = lambda key, default: (
            100 if key == "meta_rotation.min_holdout_queries" else default
        )
        mock_float.side_effect = lambda key, default: (
            1.0 if key == "meta_rotation.promotion_threshold_pct" else default
        )
        fake_row = _make_holdout(
            host_id=1,
            stage_slot="second_order_optimizer",
            algo_slug="v1",
            window_start=date.today() - timedelta(days=1),
            per_suggestion_data={"s1": _grade_data(rank=1, grade=3)},
        )
        mock_qs = mock_hq.objects.filter.return_value
        mock_qs.count.return_value = 100
        mock_qs.__iter__ = lambda self: iter([fake_row] * 100)
        META_SLOT_REGISTRY["second_order_optimizer"] = MetaSlotConfig(
            members=["lbfgs_b", "newton"],
            active_default="newton",
            rotation_mode="single_active",
        )
        mock_result.objects.filter.return_value.update.return_value = None
        mock_result.objects.update_or_create.return_value = (None, True)
        outcomes = run_meta_tournament(slot_id="second_order_optimizer")
        assert len(outcomes) == 1
        assert outcomes[0].skipped is False
