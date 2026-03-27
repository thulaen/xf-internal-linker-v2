import math
from dataclasses import replace
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.content.models import ContentItem, ScopeItem, SiloGroup
from apps.pipeline.services.click_distance import (
    ClickDistanceService,
    ClickDistanceSettings,
)
from apps.pipeline.services.feedback_rerank import (
    FeedbackRerankService,
    FeedbackRerankSettings,
)
from apps.core.models import AppSetting
from apps.graph.models import ExistingLink
from apps.pipeline.services.field_aware_relevance import (
    FieldAwareRelevanceSettings,
    evaluate_field_aware_relevance,
)
from apps.pipeline.services.learned_anchor import (
    LearnedAnchorInputRow,
    LearnedAnchorSettings,
    evaluate_learned_anchor_corroboration,
)
from apps.pipeline.services.link_freshness import (
    LinkFreshnessPeerRow,
    LinkFreshnessSettings,
    calculate_link_freshness,
    run_link_freshness,
)
from apps.pipeline.services.phrase_matching import (
    PhraseMatchingSettings,
    _build_destination_phrase_inventory,
    evaluate_phrase_match,
)
from apps.pipeline.services.rare_term_propagation import (
    RareTermPropagationSettings,
    build_rare_term_profiles,
    evaluate_rare_term_propagation,
)
from apps.pipeline.services.pipeline import _persist_diagnostics
from apps.pipeline.services.ranker import (
    ContentRecord,
    SentenceRecord,
    SentenceSemanticMatch,
    SiloSettings,
    score_destination_matches,
)
from apps.pipeline.services.weighted_pagerank import (
    _WeightedEdge,
    _normalize_source_edges,
    run_weighted_pagerank,
)
from apps.suggestions.models import PipelineDiagnostic, PipelineRun


def _content_record(
    *,
    content_id: int,
    silo_group_id: int | None,
    march_2026_pagerank_score: float = 0.0,
    link_freshness_score: float = 0.5,
    content_value_score: float = 0.0,
) -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        content_type="thread",
        title=f"Item {content_id}",
        distilled_text="Topic body",
        scope_id=content_id,
        scope_type="node",
        parent_id=None,
        parent_type="",
        grandparent_id=None,
        grandparent_type="",
        silo_group_id=silo_group_id,
        silo_group_name=f"Silo {silo_group_id}" if silo_group_id else "",
        reply_count=5,
        march_2026_pagerank_score=march_2026_pagerank_score,
        link_freshness_score=link_freshness_score,
        content_value_score=content_value_score,
        primary_post_char_count=500,
        tokens=frozenset({"topic", str(content_id)}),
    )


class SiloRankerTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=1, silo_group_id=10)
        self.same_host = _content_record(content_id=2, silo_group_id=10)
        self.cross_host = _content_record(content_id=3, silo_group_id=99)
        self.unassigned_host = _content_record(content_id=4, silo_group_id=None)
        self.sentence_records = {
            20: SentenceRecord(20, 2, "thread", "Useful same silo sentence", 80, frozenset({"topic"})),
            30: SentenceRecord(30, 3, "thread", "Useful cross silo sentence", 80, frozenset({"topic"})),
            40: SentenceRecord(40, 4, "thread", "Useful unassigned sentence", 80, frozenset({"topic"})),
        }
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.march_2026_pagerank_bounds = (0.1, 2.0)

    def test_prefer_same_silo_adjusts_scores_but_disabled_preserves_baseline(self):
        same_match = [SentenceSemanticMatch(2, "thread", 20, 0.8)]
        cross_match = [SentenceSemanticMatch(3, "thread", 30, 0.8)]
        records = {
            self.destination.key: self.destination,
            self.same_host.key: self.same_host,
            self.cross_host.key: self.cross_host,
        }

        disabled_same = score_destination_matches(
            self.destination,
            same_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="disabled"),
        )[0]
        disabled_cross = score_destination_matches(
            self.destination,
            cross_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="disabled"),
        )[0]
        preferred_same = score_destination_matches(
            self.destination,
            same_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="prefer_same_silo", same_silo_boost=0.2, cross_silo_penalty=0.1),
        )[0]
        preferred_cross = score_destination_matches(
            self.destination,
            cross_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="prefer_same_silo", same_silo_boost=0.2, cross_silo_penalty=0.1),
        )[0]

        self.assertAlmostEqual(disabled_same.score_silo_affinity, 0.0)
        self.assertAlmostEqual(disabled_cross.score_silo_affinity, 0.0)
        self.assertAlmostEqual(preferred_same.score_silo_affinity, 0.2)
        self.assertAlmostEqual(preferred_cross.score_silo_affinity, -0.1)
        self.assertGreater(preferred_same.score_final, disabled_same.score_final)
        self.assertLess(preferred_cross.score_final, disabled_cross.score_final)

    def test_strict_same_silo_blocks_only_cross_silo_and_emits_reason(self):
        cross_reasons: set[str] = set()
        unassigned_reasons: set[str] = set()
        records = {
            self.destination.key: self.destination,
            self.cross_host.key: self.cross_host,
            self.unassigned_host.key: self.unassigned_host,
        }

        cross_result = score_destination_matches(
            self.destination,
            [SentenceSemanticMatch(3, "thread", 30, 0.8)],
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="strict_same_silo"),
            blocked_reasons=cross_reasons,
        )
        unassigned_result = score_destination_matches(
            self.destination,
            [SentenceSemanticMatch(4, "thread", 40, 0.8)],
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="strict_same_silo"),
            blocked_reasons=unassigned_reasons,
        )

        self.assertEqual(cross_result, [])
        self.assertIn("cross_silo_blocked", cross_reasons)
        self.assertEqual(len(unassigned_result), 1)
        self.assertEqual(unassigned_reasons, set())

    def test_cross_silo_diagnostic_persists_machine_readable_detail(self):
        run = PipelineRun.objects.create()
        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        destination_silo = SiloGroup.objects.create(name="Guides", slug="guides")
        scope.silo_group = destination_silo
        scope.save(update_fields=["silo_group"])
        destination = ContentItem.objects.create(
            content_id=1,
            content_type="thread",
            title="Guide",
            scope=scope,
        )

        _persist_diagnostics(
            run_id=str(run.run_id),
            diagnostics=[
                (
                    destination.pk,
                    destination.content_type,
                    "cross_silo_blocked",
                    {
                        "mode": "strict_same_silo",
                        "destination_silo_group_id": destination_silo.pk,
                        "destination_silo_group_name": destination_silo.name,
                    },
                )
            ],
        )

        diagnostic = PipelineDiagnostic.objects.get()
        self.assertEqual(diagnostic.skip_reason, "cross_silo_blocked")
        self.assertEqual(diagnostic.detail["mode"], "strict_same_silo")
        self.assertEqual(diagnostic.destination_id, destination.pk)

    def test_weighted_authority_disabled_preserves_existing_ranker_output(self):
        destination = _content_record(content_id=10, silo_group_id=None, march_2026_pagerank_score=2.0)
        host = _content_record(content_id=20, silo_group_id=None)
        records = {
            destination.key: destination,
            host.key: host,
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records=self.sentence_records | {
                20: SentenceRecord(20, 20, "thread", "Useful sentence about topic", 80, frozenset({"topic"}))
            },
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            weighted_authority_ranking_weight=0.0,
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records=self.sentence_records | {
                20: SentenceRecord(20, 20, "thread", "Useful sentence about topic", 80, frozenset({"topic"}))
            },
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            weighted_authority_ranking_weight=0.25,
        )[0]

        self.assertAlmostEqual(baseline.score_final + 0.25, enabled.score_final, places=6)

    def test_weighted_authority_does_not_override_existing_link_block(self):
        destination = _content_record(content_id=10, silo_group_id=None, march_2026_pagerank_score=2.0)
        host = _content_record(content_id=20, silo_group_id=None)
        records = {
            destination.key: destination,
            host.key: host,
        }

        result = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records={
                20: SentenceRecord(20, 20, "thread", "Useful sentence about topic", 80, frozenset({"topic"}))
            },
            existing_links={((20, "thread"), (10, "thread"))},
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            weighted_authority_ranking_weight=0.25,
        )

        self.assertEqual(result, [])

    def test_link_freshness_weight_zero_and_neutral_score_have_no_effect(self):
        destination = _content_record(content_id=10, silo_group_id=None, link_freshness_score=0.5)
        fresh_destination = _content_record(content_id=10, silo_group_id=None, link_freshness_score=0.8)
        host = _content_record(content_id=20, silo_group_id=None)
        records = {
            destination.key: destination,
            host.key: host,
        }
        sentence_records = {
            20: SentenceRecord(20, 20, "thread", "Useful sentence about topic", 80, frozenset({"topic"}))
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            link_freshness_ranking_weight=0.0,
        )[0]
        neutral_enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            link_freshness_ranking_weight=0.15,
        )[0]
        fresh_enabled = score_destination_matches(
            fresh_destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records={
                fresh_destination.key: fresh_destination,
                host.key: host,
            },
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            link_freshness_ranking_weight=0.15,
        )[0]

        self.assertAlmostEqual(baseline.score_final, neutral_enabled.score_final, places=6)
        self.assertGreater(fresh_enabled.score_final, baseline.score_final)


class LinkFreshnessServiceTests(TestCase):
    def test_neutral_fallbacks_and_growth_behavior(self):
        now = timezone.now()
        settings = LinkFreshnessSettings()

        missing = calculate_link_freshness([], reference_time=now, settings=settings)
        self.assertEqual(missing.link_freshness_score, 0.5)
        self.assertEqual(missing.freshness_data_state, "neutral_missing_history")

        thin = calculate_link_freshness(
            [
                LinkFreshnessPeerRow(
                    first_seen_at=now - timedelta(days=90),
                    last_seen_at=now - timedelta(days=1),
                    last_disappeared_at=None,
                    is_active=True,
                ),
                LinkFreshnessPeerRow(
                    first_seen_at=now - timedelta(days=60),
                    last_seen_at=now - timedelta(days=1),
                    last_disappeared_at=None,
                    is_active=True,
                ),
            ],
            reference_time=now,
            settings=settings,
        )
        self.assertEqual(thin.link_freshness_score, 0.5)
        self.assertEqual(thin.freshness_data_state, "neutral_thin_history")

        growing = calculate_link_freshness(
            [
                LinkFreshnessPeerRow(now - timedelta(days=75), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=65), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=15), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=10), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=5), now - timedelta(days=1), None, True),
            ],
            reference_time=now,
            settings=settings,
        )
        cooling = calculate_link_freshness(
            [
                LinkFreshnessPeerRow(now - timedelta(days=90), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=55), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=50), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=45), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=5), now - timedelta(days=1), None, True),
            ],
            reference_time=now,
            settings=settings,
        )

        self.assertGreater(growing.link_freshness_score, 0.5)
        self.assertLess(cooling.link_freshness_score, 0.5)

    def test_recent_disappearances_reduce_score_and_recalc_does_not_touch_pagerank(self):
        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        destination = ContentItem.objects.create(
            content_id=1,
            content_type="thread",
            title="Destination",
            scope=scope,
            march_2026_pagerank_score=0.77,
        )
        sources = [
            ContentItem.objects.create(content_id=index + 2, content_type="thread", title=f"Source {index}", scope=scope)
            for index in range(4)
        ]
        now = timezone.now()
        from apps.graph.models import LinkFreshnessEdge

        for index, source in enumerate(sources):
            LinkFreshnessEdge.objects.create(
                from_content_item=source,
                to_content_item=destination,
                first_seen_at=now - timedelta(days=70 - (index * 5)),
                last_seen_at=now - timedelta(days=1),
                is_active=True,
            )

        baseline = run_link_freshness(reference_time=now)
        destination.refresh_from_db()
        baseline_score = destination.link_freshness_score

        LinkFreshnessEdge.objects.filter(from_content_item=sources[0]).update(
            is_active=False,
            last_disappeared_at=now - timedelta(days=2),
        )
        LinkFreshnessEdge.objects.filter(from_content_item=sources[1]).update(
            is_active=False,
            last_disappeared_at=now - timedelta(days=3),
        )

        diagnostics = run_link_freshness(reference_time=now)
        destination.refresh_from_db()

        self.assertIn("computed_count", baseline)
        self.assertIn("computed_count", diagnostics)
        self.assertLess(destination.link_freshness_score, baseline_score)
        self.assertAlmostEqual(destination.march_2026_pagerank_score, 0.77, places=6)

    def test_link_freshness_ignores_weighted_authority_and_velocity_settings(self):
        scope = ScopeItem.objects.create(scope_id=9, scope_type="node", title="Forum")
        destination = ContentItem.objects.create(content_id=90, content_type="thread", title="Destination", scope=scope)
        source_a = ContentItem.objects.create(content_id=91, content_type="thread", title="Source A", scope=scope)
        source_b = ContentItem.objects.create(content_id=92, content_type="thread", title="Source B", scope=scope)
        source_c = ContentItem.objects.create(content_id=93, content_type="thread", title="Source C", scope=scope)
        now = timezone.now()
        from apps.graph.models import LinkFreshnessEdge

        LinkFreshnessEdge.objects.bulk_create(
            [
                LinkFreshnessEdge(from_content_item=source_a, to_content_item=destination, first_seen_at=now - timedelta(days=80), last_seen_at=now - timedelta(days=1), is_active=True),
                LinkFreshnessEdge(from_content_item=source_b, to_content_item=destination, first_seen_at=now - timedelta(days=50), last_seen_at=now - timedelta(days=1), is_active=True),
                LinkFreshnessEdge(from_content_item=source_c, to_content_item=destination, first_seen_at=now - timedelta(days=10), last_seen_at=now - timedelta(days=1), is_active=True),
            ]
        )

        run_link_freshness(reference_time=now)
        destination.refresh_from_db()
        baseline = destination.link_freshness_score

        AppSetting.objects.create(
            key="weighted_authority.position_bias",
            value="0.9",
            value_type="float",
            category="ml",
            description="Unrelated weighted authority setting",
        )
        AppSetting.objects.create(
            key="vel_recency_half_life_days",
            value="99",
            value_type="float",
            category="ml",
            description="Unrelated velocity setting",
        )

        run_link_freshness(reference_time=now)
        destination.refresh_from_db()
        self.assertAlmostEqual(destination.link_freshness_score, baseline, places=6)


class PhraseMatchingServiceTests(TestCase):
    def test_destination_phrase_inventory_is_bounded_and_prefers_complete_phrases(self):
        phrases = _build_destination_phrase_inventory(
            destination_title="Internal Linking Guide",
            destination_distilled_text=(
                "Helpful examples for editors. "
                "Phrase block one. Phrase block two. Phrase block three. Phrase block four. "
                "Phrase block five. Phrase block six. Phrase block seven. Phrase block eight. "
                "Phrase block nine. Phrase block ten. Phrase block eleven. Phrase block twelve."
            ),
        )

        token_lists = [phrase.tokens for phrase in phrases]
        self.assertLessEqual(len(phrases), 24)
        self.assertIn(("internal", "linking", "guide"), token_lists)
        self.assertNotIn(("internal", "linking"), token_lists)

    def test_exact_title_and_distilled_phrase_matching(self):
        exact_title = evaluate_phrase_match(
            host_sentence_text="This sentence explains the internal linking guide clearly.",
            destination_title="Internal Linking Guide",
            destination_distilled_text="Helpful overview text.",
            settings=PhraseMatchingSettings(),
        )
        exact_distilled = evaluate_phrase_match(
            host_sentence_text="The article walks through anchor expansion rules step by step.",
            destination_title="Internal Linking",
            destination_distilled_text="Anchor expansion rules for safer internal links.",
            settings=PhraseMatchingSettings(),
        )

        self.assertGreater(exact_title.score_phrase_relevance, 0.5)
        self.assertEqual(exact_title.anchor_confidence, "strong")
        self.assertEqual(
            exact_title.phrase_match_diagnostics["phrase_match_state"],
            "computed_exact_title",
        )
        self.assertGreater(exact_distilled.score_phrase_relevance, 0.5)
        self.assertEqual(exact_distilled.anchor_phrase, "anchor expansion rules")
        self.assertEqual(
            exact_distilled.phrase_match_diagnostics["phrase_match_state"],
            "computed_exact_distilled",
        )

    def test_partial_match_needs_local_corroboration(self):
        accepted = evaluate_phrase_match(
            host_sentence_text="The anchor expansion workflow keeps rules nearby for editors.",
            destination_title="Editorial Linking",
            destination_distilled_text="Anchor expansion rules for editors.",
            settings=PhraseMatchingSettings(),
        )
        neutral = evaluate_phrase_match(
            host_sentence_text="The anchor expansion workflow helps editors every day.",
            destination_title="Editorial Linking",
            destination_distilled_text="Anchor expansion rules for editors.",
            settings=PhraseMatchingSettings(),
        )

        self.assertGreater(accepted.score_phrase_relevance, 0.5)
        self.assertEqual(accepted.anchor_confidence, "weak")
        self.assertEqual(
            accepted.phrase_match_diagnostics["phrase_match_state"],
            "computed_partial_distilled",
        )
        self.assertEqual(neutral.score_phrase_relevance, 0.5)
        self.assertEqual(neutral.anchor_confidence, "none")
        self.assertEqual(
            neutral.phrase_match_diagnostics["phrase_match_state"],
            "neutral_partial_below_threshold",
        )

    def test_neutral_fallback_and_anchor_expansion_rollback(self):
        no_phrases = evaluate_phrase_match(
            host_sentence_text="Tiny words only.",
            destination_title="A An The",
            destination_distilled_text="Of To In",
            settings=PhraseMatchingSettings(),
        )
        fallback = evaluate_phrase_match(
            host_sentence_text="This guide covers synthesizers in detail.",
            destination_title="Synthesizers",
            destination_distilled_text="Extra supporting text.",
            settings=PhraseMatchingSettings(enable_anchor_expansion=False),
        )

        self.assertEqual(no_phrases.score_phrase_relevance, 0.5)
        self.assertEqual(
            no_phrases.phrase_match_diagnostics["phrase_match_state"],
            "neutral_no_destination_phrases",
        )
        self.assertEqual(fallback.anchor_phrase, "synthesizers")
        self.assertEqual(
            fallback.phrase_match_diagnostics["phrase_match_state"],
            "fallback_current_extractor",
        )

    def test_longer_complete_phrase_wins(self):
        result = evaluate_phrase_match(
            host_sentence_text="This internal linking guide explains the full workflow.",
            destination_title="Internal Linking Guide",
            destination_distilled_text="Helpful notes.",
            settings=PhraseMatchingSettings(),
        )

        self.assertEqual(result.anchor_phrase, "internal linking guide")


class LearnedAnchorServiceTests(TestCase):
    def test_exact_family_and_host_canonical_states_are_explainable(self):
        rows = [
            LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
            LearnedAnchorInputRow(source_content_id=2, anchor_text="Internal Linking Guide"),
            LearnedAnchorInputRow(source_content_id=3, anchor_text="Internal Linking Guides"),
            LearnedAnchorInputRow(source_content_id=4, anchor_text="click here"),
        ]

        exact = evaluate_learned_anchor_corroboration(
            candidate_anchor_text="Internal Linking Guide",
            host_sentence_text="This internal linking guide helps editors.",
            inbound_anchor_rows=rows,
            settings=LearnedAnchorSettings(),
        )
        family = evaluate_learned_anchor_corroboration(
            candidate_anchor_text="Internal Linking",
            host_sentence_text="This internal linking helps editors.",
            inbound_anchor_rows=rows,
            settings=LearnedAnchorSettings(),
        )
        host_contains = evaluate_learned_anchor_corroboration(
            candidate_anchor_text="Editor workflow",
            host_sentence_text="This internal linking guide helps editors.",
            inbound_anchor_rows=rows,
            settings=LearnedAnchorSettings(),
        )

        self.assertGreater(exact.score_learned_anchor_corroboration, 0.5)
        self.assertEqual(exact.learned_anchor_diagnostics["learned_anchor_state"], "exact_variant_match")
        self.assertEqual(exact.learned_anchor_diagnostics["usable_inbound_anchor_sources"], 3)
        self.assertGreater(family.score_learned_anchor_corroboration, 0.5)
        self.assertEqual(family.learned_anchor_diagnostics["learned_anchor_state"], "family_match")
        self.assertEqual(host_contains.score_learned_anchor_corroboration, 0.5)
        self.assertEqual(host_contains.learned_anchor_diagnostics["learned_anchor_state"], "host_contains_canonical_variant")
        self.assertEqual(host_contains.learned_anchor_diagnostics["recommended_canonical_anchor"], "Internal Linking Guide")

    def test_thin_history_stays_neutral(self):
        result = evaluate_learned_anchor_corroboration(
            candidate_anchor_text="Internal Linking Guide",
            host_sentence_text="This internal linking guide helps editors.",
            inbound_anchor_rows=[
                LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
            ],
            settings=LearnedAnchorSettings(minimum_anchor_sources=2),
        )

        self.assertEqual(result.score_learned_anchor_corroboration, 0.5)
        self.assertEqual(result.learned_anchor_diagnostics["learned_anchor_state"], "neutral_below_min_sources")


class PhraseRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=101, silo_group_id=None)
        self.host = _content_record(content_id=202, silo_group_id=None)
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)

    def test_phrase_weight_zero_keeps_ranking_unchanged_and_positive_weight_adds_signal(self):
        destination = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Anchor expansion tips for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=self.destination.march_2026_pagerank_score,
            link_freshness_score=self.destination.link_freshness_score,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"internal", "linking", "guide"}),
        )
        host = self.host
        records = {destination.key: destination, host.key: host}
        sentence_records = {
            20: SentenceRecord(
                20,
                host.content_id,
                host.content_type,
                "The internal linking guide gives anchor expansion tips.",
                80,
                frozenset({"internal", "linking", "guide", "anchor", "expansion"}),
            )
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 20, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            phrase_matching_settings=PhraseMatchingSettings(ranking_weight=0.0),
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 20, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            phrase_matching_settings=PhraseMatchingSettings(ranking_weight=0.1),
        )[0]

        self.assertGreater(baseline.score_phrase_relevance, 0.5)
        self.assertAlmostEqual(
            enabled.score_final,
            baseline.score_final + 0.1 * (2 * (baseline.score_phrase_relevance - 0.5)),
            places=6,
        )

    def test_phrase_signal_ignores_weighted_authority_freshness_and_velocity_inputs(self):
        destination_a = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Anchor Expansion Rules",
            distilled_text="Anchor expansion rules for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=0.1,
            link_freshness_score=0.2,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"anchor", "expansion", "rules"}),
        )
        destination_b = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Anchor Expansion Rules",
            distilled_text="Anchor expansion rules for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=2.0,
            link_freshness_score=0.9,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"anchor", "expansion", "rules"}),
        )
        host = ContentRecord(
            content_id=self.host.content_id,
            content_type=self.host.content_type,
            title=self.host.title,
            distilled_text=self.host.distilled_text,
            scope_id=self.host.scope_id,
            scope_type=self.host.scope_type,
            parent_id=self.host.parent_id,
            parent_type=self.host.parent_type,
            grandparent_id=self.host.grandparent_id,
            grandparent_type=self.host.grandparent_type,
            silo_group_id=self.host.silo_group_id,
            silo_group_name=self.host.silo_group_name,
            reply_count=99,
            march_2026_pagerank_score=1.8,
            link_freshness_score=self.host.link_freshness_score,
            primary_post_char_count=900,
            tokens=self.host.tokens,
        )
        sentence_records = {
            30: SentenceRecord(
                30,
                host.content_id,
                host.content_type,
                "The anchor expansion rules help editors write natural links.",
                80,
                frozenset({"anchor", "expansion", "rules", "editors"}),
            )
        }

        result_a = score_destination_matches(
            destination_a,
            [SentenceSemanticMatch(host.content_id, host.content_type, 30, 0.8)],
            content_records={destination_a.key: destination_a, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            weighted_authority_ranking_weight=0.25,
            link_freshness_ranking_weight=0.15,
            phrase_matching_settings=PhraseMatchingSettings(ranking_weight=0.0),
        )[0]
        result_b = score_destination_matches(
            destination_b,
            [SentenceSemanticMatch(host.content_id, host.content_type, 30, 0.8)],
            content_records={destination_b.key: destination_b, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            weighted_authority_ranking_weight=0.25,
            link_freshness_ranking_weight=0.15,
            phrase_matching_settings=PhraseMatchingSettings(ranking_weight=0.0),
        )[0]

        self.assertAlmostEqual(result_a.score_phrase_relevance, result_b.score_phrase_relevance, places=6)
        self.assertEqual(result_a.anchor_phrase, result_b.anchor_phrase)


class LearnedAnchorRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=301, silo_group_id=None)
        self.host = _content_record(content_id=302, silo_group_id=None)
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)
        self.learned_rows = {
            self.destination.key: [
                LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
                LearnedAnchorInputRow(source_content_id=2, anchor_text="Internal Linking Guide"),
                LearnedAnchorInputRow(source_content_id=3, anchor_text="Internal Linking Guides"),
            ]
        }

    def test_learned_anchor_weight_zero_keeps_ranking_unchanged_and_positive_weight_adds_signal(self):
        destination = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Internal linking guide notes for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=self.destination.march_2026_pagerank_score,
            link_freshness_score=self.destination.link_freshness_score,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"internal", "linking", "guide"}),
        )
        records = {destination.key: destination, self.host.key: self.host}
        sentence_records = {
            40: SentenceRecord(
                40,
                self.host.content_id,
                self.host.content_type,
                "The internal linking guide gives editors a safe anchor pattern.",
                80,
                frozenset({"internal", "linking", "guide", "editors", "anchor"}),
            )
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(self.host.content_id, self.host.content_type, 40, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            learned_anchor_settings=LearnedAnchorSettings(ranking_weight=0.0),
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(self.host.content_id, self.host.content_type, 40, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            learned_anchor_settings=LearnedAnchorSettings(ranking_weight=0.1),
        )[0]

        self.assertGreater(baseline.score_learned_anchor_corroboration, 0.5)
        self.assertAlmostEqual(
            enabled.score_final,
            baseline.score_final + 0.1 * (2 * (baseline.score_learned_anchor_corroboration - 0.5)),
            places=6,
        )

    def test_learned_anchor_signal_ignores_authority_freshness_and_velocity_inputs(self):
        destination_a = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Internal linking guide notes for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=0.1,
            link_freshness_score=0.2,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"internal", "linking", "guide"}),
        )
        destination_b = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Internal linking guide notes for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=2.0,
            link_freshness_score=0.9,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"internal", "linking", "guide"}),
        )
        host = ContentRecord(
            content_id=self.host.content_id,
            content_type=self.host.content_type,
            title=self.host.title,
            distilled_text=self.host.distilled_text,
            scope_id=self.host.scope_id,
            scope_type=self.host.scope_type,
            parent_id=self.host.parent_id,
            parent_type=self.host.parent_type,
            grandparent_id=self.host.grandparent_id,
            grandparent_type=self.host.grandparent_type,
            silo_group_id=self.host.silo_group_id,
            silo_group_name=self.host.silo_group_name,
            reply_count=99,
            march_2026_pagerank_score=1.8,
            link_freshness_score=self.host.link_freshness_score,
            primary_post_char_count=900,
            tokens=self.host.tokens,
        )
        sentence_records = {
            41: SentenceRecord(
                41,
                host.content_id,
                host.content_type,
                "The internal linking guide gives editors a safe anchor pattern.",
                80,
                frozenset({"internal", "linking", "guide", "editors", "anchor"}),
            )
        }

        result_a = score_destination_matches(
            destination_a,
            [SentenceSemanticMatch(host.content_id, host.content_type, 41, 0.8)],
            content_records={destination_a.key: destination_a, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            weighted_authority_ranking_weight=0.25,
            link_freshness_ranking_weight=0.15,
            learned_anchor_settings=LearnedAnchorSettings(ranking_weight=0.0),
        )[0]
        result_b = score_destination_matches(
            destination_b,
            [SentenceSemanticMatch(host.content_id, host.content_type, 41, 0.8)],
            content_records={destination_b.key: destination_b, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            weighted_authority_ranking_weight=0.25,
            link_freshness_ranking_weight=0.15,
            learned_anchor_settings=LearnedAnchorSettings(ranking_weight=0.0),
        )[0]

        self.assertAlmostEqual(
            result_a.score_learned_anchor_corroboration,
            result_b.score_learned_anchor_corroboration,
            places=6,
        )
        self.assertEqual(
            result_a.learned_anchor_diagnostics["matched_family_canonical"],
            result_b.learned_anchor_diagnostics["matched_family_canonical"],
        )


class RareTermPropagationServiceTests(TestCase):
    def _record(
        self,
        *,
        content_id: int,
        scope_id: int,
        parent_id: int | None,
        grandparent_id: int | None,
        silo_group_id: int | None,
        tokens: frozenset[str],
    ) -> ContentRecord:
        return ContentRecord(
            content_id=content_id,
            content_type="thread",
            title=f"Item {content_id}",
            distilled_text="Topic body",
            scope_id=scope_id,
            scope_type="node",
            parent_id=parent_id,
            parent_type="category" if parent_id is not None else "",
            grandparent_id=grandparent_id,
            grandparent_type="category" if grandparent_id is not None else "",
            silo_group_id=silo_group_id,
            silo_group_name=f"Silo {silo_group_id}" if silo_group_id else "",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=tokens,
        )

    def test_related_page_boundaries_and_rare_term_thresholds(self):
        destination = self._record(
            content_id=1,
            scope_id=10,
            parent_id=100,
            grandparent_id=1000,
            silo_group_id=1,
            tokens=frozenset({"guide", "topic"}),
        )
        same_scope = self._record(
            content_id=2,
            scope_id=10,
            parent_id=101,
            grandparent_id=1001,
            silo_group_id=1,
            tokens=frozenset({"guide", "xenforo", "plugin"}),
        )
        same_parent_one_shared = self._record(
            content_id=3,
            scope_id=11,
            parent_id=100,
            grandparent_id=1002,
            silo_group_id=1,
            tokens=frozenset({"guide", "solr"}),
        )
        same_parent_two_shared = self._record(
            content_id=4,
            scope_id=12,
            parent_id=100,
            grandparent_id=1003,
            silo_group_id=1,
            tokens=frozenset({"guide", "topic", "xenforo", "plugin"}),
        )
        same_grandparent_two_shared = self._record(
            content_id=5,
            scope_id=13,
            parent_id=102,
            grandparent_id=1000,
            silo_group_id=1,
            tokens=frozenset({"guide", "topic", "plugin"}),
        )
        cross_silo = self._record(
            content_id=6,
            scope_id=10,
            parent_id=100,
            grandparent_id=1000,
            silo_group_id=9,
            tokens=frozenset({"guide", "topic", "xenforo"}),
        )
        plugin_extra_a = self._record(
            content_id=7,
            scope_id=20,
            parent_id=200,
            grandparent_id=2000,
            silo_group_id=None,
            tokens=frozenset({"plugin", "alpha"}),
        )
        plugin_extra_b = self._record(
            content_id=8,
            scope_id=21,
            parent_id=201,
            grandparent_id=2001,
            silo_group_id=None,
            tokens=frozenset({"plugin", "beta"}),
        )

        profiles = build_rare_term_profiles(
            {
                record.key: record
                for record in [
                    destination,
                    same_scope,
                    same_parent_one_shared,
                    same_parent_two_shared,
                    same_grandparent_two_shared,
                    cross_silo,
                    plugin_extra_a,
                    plugin_extra_b,
                ]
            },
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )

        profile = profiles[destination.key]
        self.assertEqual(profile.eligible_related_page_count, 3)
        self.assertEqual(
            [row.content_id for row in profile.related_page_summary],
            [2, 4, 5],
        )
        self.assertEqual(
            [term.term for term in profile.propagated_terms],
            ["xenforo"],
        )

    def test_duplicate_counting_and_destination_separation_stay_safe(self):
        destination = self._record(
            content_id=20,
            scope_id=30,
            parent_id=300,
            grandparent_id=3000,
            silo_group_id=None,
            tokens=frozenset({"guide", "topic", "xenforo"}),
        )
        donor_a = self._record(
            content_id=21,
            scope_id=30,
            parent_id=301,
            grandparent_id=3001,
            silo_group_id=None,
            tokens=frozenset({"guide", "xenforo", "solr"}),
        )
        donor_b = self._record(
            content_id=22,
            scope_id=30,
            parent_id=302,
            grandparent_id=3002,
            silo_group_id=None,
            tokens=frozenset({"topic", "xenforo", "solr"}),
        )

        profiles = build_rare_term_profiles(
            {record.key: record for record in [destination, donor_a, donor_b]},
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        profile = profiles[destination.key]
        self.assertEqual(profile.profile_state, "neutral_no_rare_terms")
        self.assertEqual(profile.propagated_terms, ())

        thin_destination = self._record(
            content_id=23,
            scope_id=31,
            parent_id=310,
            grandparent_id=3100,
            silo_group_id=None,
            tokens=frozenset({"guide", "topic"}),
        )
        thin_donor = self._record(
            content_id=24,
            scope_id=31,
            parent_id=311,
            grandparent_id=3101,
            silo_group_id=None,
            tokens=frozenset({"guide", "xenforo"}),
        )
        thin_profiles = build_rare_term_profiles(
            {record.key: record for record in [thin_destination, thin_donor]},
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        thin_result = evaluate_rare_term_propagation(
            destination=thin_destination,
            host_sentence_tokens=frozenset({"xenforo"}),
            profiles=thin_profiles,
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        self.assertEqual(thin_result.score_rare_term_propagation, 0.5)
        self.assertEqual(thin_result.rare_term_state, "neutral_below_min_support")

        supported_destination = self._record(
            content_id=25,
            scope_id=32,
            parent_id=320,
            grandparent_id=3200,
            silo_group_id=None,
            tokens=frozenset({"guide", "topic"}),
        )
        supported_donor_a = self._record(
            content_id=26,
            scope_id=32,
            parent_id=321,
            grandparent_id=3201,
            silo_group_id=None,
            tokens=frozenset({"guide", "xenforo"}),
        )
        supported_donor_b = self._record(
            content_id=27,
            scope_id=32,
            parent_id=322,
            grandparent_id=3202,
            silo_group_id=None,
            tokens=frozenset({"topic", "xenforo"}),
        )
        supported_profiles = build_rare_term_profiles(
            {
                record.key: record
                for record in [supported_destination, supported_donor_a, supported_donor_b]
            },
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        supported_result = evaluate_rare_term_propagation(
            destination=supported_destination,
            host_sentence_tokens=frozenset({"xenforo"}),
            profiles=supported_profiles,
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        self.assertGreater(supported_result.score_rare_term_propagation, 0.5)
        self.assertEqual(len(supported_result.rare_term_diagnostics["matched_propagated_terms"]), 1)
        self.assertEqual(
            supported_result.rare_term_diagnostics["matched_propagated_terms"][0]["supporting_related_pages"],
            2,
        )

    def test_disabled_feature_stays_neutral(self):
        destination = self._record(
            content_id=40,
            scope_id=40,
            parent_id=400,
            grandparent_id=4000,
            silo_group_id=None,
            tokens=frozenset({"guide", "topic"}),
        )

        result = evaluate_rare_term_propagation(
            destination=destination,
            host_sentence_tokens=frozenset({"xenforo"}),
            profiles={},
            settings=RareTermPropagationSettings(enabled=False),
        )

        self.assertEqual(result.score_rare_term_propagation, 0.5)
        self.assertEqual(result.rare_term_state, "neutral_feature_disabled")
        self.assertEqual(result.rare_term_diagnostics, {})


class RareTermRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=401, silo_group_id=None)
        self.host = _content_record(content_id=402, silo_group_id=None)
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)

    def test_rare_term_weight_zero_is_a_ranking_no_op(self):
        destination = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Link Guide",
            distilled_text="Internal link guide for editors.",
            scope_id=500,
            scope_type="node",
            parent_id=900,
            parent_type="category",
            grandparent_id=1200,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"guide", "internal", "link"}),
        )
        donor_a = ContentRecord(
            content_id=403,
            content_type="thread",
            title="XenForo linking notes",
            distilled_text="Guide xenforo notes.",
            scope_id=500,
            scope_type="node",
            parent_id=901,
            parent_type="category",
            grandparent_id=1201,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"guide", "xenforo"}),
        )
        donor_b = ContentRecord(
            content_id=404,
            content_type="thread",
            title="Topic xenforo setup",
            distilled_text="Link xenforo setup.",
            scope_id=500,
            scope_type="node",
            parent_id=902,
            parent_type="category",
            grandparent_id=1202,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"link", "xenforo"}),
        )
        host = ContentRecord(
            content_id=self.host.content_id,
            content_type=self.host.content_type,
            title=self.host.title,
            distilled_text=self.host.distilled_text,
            scope_id=self.host.scope_id,
            scope_type=self.host.scope_type,
            parent_id=self.host.parent_id,
            parent_type=self.host.parent_type,
            grandparent_id=self.host.grandparent_id,
            grandparent_type=self.host.grandparent_type,
            silo_group_id=self.host.silo_group_id,
            silo_group_name=self.host.silo_group_name,
            reply_count=99,
            march_2026_pagerank_score=1.8,
            link_freshness_score=self.host.link_freshness_score,
            primary_post_char_count=900,
            tokens=frozenset({"guide", "link", "xenforo"}),
        )
        sentence_records = {
            50: SentenceRecord(
                50,
                host.content_id,
                host.content_type,
                "This xenforo xenforo guide helps editors manage internal links.",
                80,
                frozenset({"guide", "link", "xenforo", "editors", "internal"}),
            )
        }
        rare_term_profiles = build_rare_term_profiles(
            {
                record.key: record
                for record in [destination, donor_a, donor_b]
            },
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 50, 0.8)],
            content_records={destination.key: destination, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            rare_term_profiles=rare_term_profiles,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            rare_term_settings=RareTermPropagationSettings(
                ranking_weight=0.0,
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 50, 0.8)],
            content_records={destination.key: destination, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            rare_term_profiles=rare_term_profiles,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            rare_term_settings=RareTermPropagationSettings(
                ranking_weight=0.05,
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )[0]

        self.assertGreater(baseline.score_rare_term_propagation, 0.5)
        self.assertEqual(
            len(baseline.rare_term_diagnostics["matched_propagated_terms"]),
            1,
        )
        self.assertAlmostEqual(
            enabled.score_final,
            baseline.score_final + 0.05 * (2 * (baseline.score_rare_term_propagation - 0.5)),
            places=6,
        )


class FieldAwareRelevanceServiceTests(TestCase):
    def test_field_aware_relevance_matches_title_body_and_scope_separately(self):
        destination = ContentRecord(
            content_id=501,
            content_type="thread",
            title="Internal Linking Guide",
            distilled_text="Safe editor workflow for internal links.",
            scope_id=10,
            scope_type="node",
            parent_id=100,
            parent_type="category",
            grandparent_id=1000,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"internal", "linking", "guide"}),
            scope_title="Guides",
            parent_scope_title="SEO",
            grandparent_scope_title="Marketing",
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="This internal linking guide helps editor workflow inside the SEO guides area.",
            inbound_anchor_rows=[
                LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
                LearnedAnchorInputRow(source_content_id=2, anchor_text="Internal Linking Guide"),
            ],
            settings=FieldAwareRelevanceSettings(),
        )

        self.assertGreater(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_state, "computed_match")
        self.assertGreater(result.field_aware_diagnostics["field_scores"]["title"]["score"], 0.0)
        self.assertGreater(result.field_aware_diagnostics["field_scores"]["body"]["score"], 0.0)
        self.assertGreater(result.field_aware_diagnostics["field_scores"]["scope"]["score"], 0.0)

    def test_field_aware_relevance_stays_neutral_without_matches(self):
        destination = _content_record(content_id=502, silo_group_id=None)

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="Completely unrelated sentence about oranges and bicycles.",
            inbound_anchor_rows=[],
            settings=FieldAwareRelevanceSettings(),
        )

        self.assertEqual(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_state, "neutral_no_field_matches")


class FieldAwareRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=601, silo_group_id=None)
        self.host = _content_record(content_id=602, silo_group_id=None)
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)
        self.learned_rows = {
            self.destination.key: [
                LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
                LearnedAnchorInputRow(source_content_id=2, anchor_text="Guide"),
            ]
        }

    def test_field_aware_weight_zero_is_a_ranking_no_op(self):
        destination = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Internal link guide for editors.",
            scope_id=500,
            scope_type="node",
            parent_id=900,
            parent_type="category",
            grandparent_id=1200,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"guide", "internal", "link"}),
            scope_title="Guides",
            parent_scope_title="SEO",
            grandparent_scope_title="Marketing",
        )
        host = ContentRecord(
            content_id=self.host.content_id,
            content_type=self.host.content_type,
            title=self.host.title,
            distilled_text=self.host.distilled_text,
            scope_id=self.host.scope_id,
            scope_type=self.host.scope_type,
            parent_id=self.host.parent_id,
            parent_type=self.host.parent_type,
            grandparent_id=self.host.grandparent_id,
            grandparent_type=self.host.grandparent_type,
            silo_group_id=self.host.silo_group_id,
            silo_group_name=self.host.silo_group_name,
            reply_count=99,
            march_2026_pagerank_score=1.8,
            link_freshness_score=self.host.link_freshness_score,
            primary_post_char_count=900,
            tokens=frozenset({"guide", "link", "seo", "internal"}),
        )
        sentence_records = {
            60: SentenceRecord(
                60,
                host.content_id,
                host.content_type,
                "This internal linking guide helps SEO editors improve internal links.",
                80,
                frozenset({"internal", "linking", "guide", "seo", "editors", "links"}),
            )
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 60, 0.8)],
            content_records={destination.key: destination, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            field_aware_settings=FieldAwareRelevanceSettings(ranking_weight=0.0),
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 60, 0.8)],
            content_records={destination.key: destination, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            field_aware_settings=FieldAwareRelevanceSettings(ranking_weight=0.05),
        )[0]

        self.assertGreater(baseline.score_field_aware_relevance, 0.5)
        self.assertAlmostEqual(
            enabled.score_final,
            baseline.score_final + 0.05 * (2 * (baseline.score_field_aware_relevance - 0.5)),
            places=6,
        )


class WeightedAuthorityGraphTests(TestCase):
    def setUp(self):
        self.scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")

    def _content(self, content_id: int, title: str) -> ContentItem:
        return ContentItem.objects.create(
            content_id=content_id,
            content_type="thread",
            title=title,
            scope=self.scope,
        )

    def test_uniform_weight_behavior_populates_march_2026_pagerank_score(self):
        a = self._content(1, "A")
        b = self._content(2, "B")
        c = self._content(3, "C")

        ExistingLink.objects.create(
            from_content_item=a,
            to_content_item=b,
            anchor_text="B",
            extraction_method="html_anchor",
            link_ordinal=0,
            source_internal_link_count=2,
            context_class="contextual",
        )
        ExistingLink.objects.create(
            from_content_item=a,
            to_content_item=c,
            anchor_text="C",
            extraction_method="html_anchor",
            link_ordinal=1,
            source_internal_link_count=2,
            context_class="contextual",
        )
        ExistingLink.objects.create(
            from_content_item=b,
            to_content_item=c,
            anchor_text="C",
            extraction_method="html_anchor",
            link_ordinal=0,
            source_internal_link_count=1,
            context_class="contextual",
        )
        ExistingLink.objects.create(
            from_content_item=c,
            to_content_item=a,
            anchor_text="A",
            extraction_method="html_anchor",
            link_ordinal=0,
            source_internal_link_count=1,
            context_class="contextual",
        )

        diagnostics = run_weighted_pagerank(
            settings_map={
                "position_bias": 0.0,
                "empty_anchor_factor": 1.0,
                "bare_url_factor": 1.0,
                "weak_context_factor": 1.0,
                "isolated_context_factor": 1.0,
            }
        )

        march_2026_scores = {
            item.pk: item.march_2026_pagerank_score
            for item in ContentItem.objects.order_by("pk")
        }

        self.assertEqual(diagnostics["fallback_row_count"], 0)
        self.assertTrue(all(score >= 0.0 for score in march_2026_scores.values()))
        self.assertAlmostEqual(sum(march_2026_scores.values()), 1.0, places=6)

    def test_outbound_normalization_boilerplate_downweight_and_contextual_upweight(self):
        probabilities, used_fallback = _normalize_source_edges(
            [
                _WeightedEdge(
                    source_index=0,
                    target_index=1,
                    anchor_text="Editorial link",
                    extraction_method="html_anchor",
                    link_ordinal=0,
                    source_internal_link_count=2,
                    context_class="contextual",
                    pk=1,
                ),
                _WeightedEdge(
                    source_index=0,
                    target_index=2,
                    anchor_text="",
                    extraction_method="bare_url",
                    link_ordinal=1,
                    source_internal_link_count=2,
                    context_class="isolated",
                    pk=2,
                ),
            ],
            settings_map={
                "position_bias": 0.5,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )

        self.assertFalse(used_fallback)
        self.assertGreater(probabilities[0], probabilities[1])
        self.assertAlmostEqual(sum(probabilities), 1.0, places=6)

    def test_monotonicity_improving_context_increases_edge_probability(self):
        baseline_probabilities, _ = _normalize_source_edges(
            [
                _WeightedEdge(0, 1, "A", "html_anchor", 0, 2, "weak_context", 1),
                _WeightedEdge(0, 2, "B", "html_anchor", 1, 2, "contextual", 2),
            ],
            settings_map={
                "position_bias": 0.0,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )
        improved_probabilities, _ = _normalize_source_edges(
            [
                _WeightedEdge(0, 1, "A", "html_anchor", 0, 2, "contextual", 1),
                _WeightedEdge(0, 2, "B", "html_anchor", 1, 2, "contextual", 2),
            ],
            settings_map={
                "position_bias": 0.0,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )

        self.assertGreater(improved_probabilities[0], baseline_probabilities[0])

    def test_missing_feature_rows_fallback_to_neutral_uniform_behavior(self):
        probabilities, used_fallback = _normalize_source_edges(
            [
                _WeightedEdge(0, 1, "First", "", None, None, "", 1),
                _WeightedEdge(0, 2, "Second", "", None, None, "", 2),
            ],
            settings_map={
                "position_bias": 0.5,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )

        self.assertFalse(used_fallback)
        self.assertAlmostEqual(probabilities[0], 0.5, places=6)
        self.assertAlmostEqual(probabilities[1], 0.5, places=6)

    def test_nonfinite_rows_fallback_to_uniform_probabilities(self):
        probabilities, used_fallback = _normalize_source_edges(
            [
                _WeightedEdge(0, 1, "First", "html_anchor", 0, 2, "contextual", 1),
                _WeightedEdge(0, 2, "Second", "html_anchor", 1, 2, "contextual", 2),
            ],
            settings_map={
                "position_bias": math.inf,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )

        self.assertTrue(used_fallback)
        self.assertAlmostEqual(probabilities[0], 0.5, places=6)
        self.assertAlmostEqual(probabilities[1], 0.5, places=6)


class ClickDistanceServiceTests(TestCase):
    def test_url_depth_calculation(self):
        service = ClickDistanceService()
        self.assertEqual(service.calculate_url_depth("https://example.com/"), 0)
        self.assertEqual(service.calculate_url_depth("https://example.com/item/"), 1)
        self.assertEqual(service.calculate_url_depth("https://example.com/path/to/item"), 3)
        self.assertEqual(service.calculate_url_depth(""), 0)

    def test_scope_depth_map_building(self):
        root = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Root")
        child = ScopeItem.objects.create(scope_id=2, scope_type="node", title="Child", parent=root)
        grandchild = ScopeItem.objects.create(scope_id=3, scope_type="node", title="Grandchild", parent=child)
        standalone = ScopeItem.objects.create(scope_id=4, scope_type="node", title="Standalone")

        service = ClickDistanceService()
        depth_map = service.build_scope_depth_map()

        self.assertEqual(depth_map[root.id], 0)
        self.assertEqual(depth_map[child.id], 1)
        self.assertEqual(depth_map[grandchild.id], 2)
        self.assertEqual(depth_map[standalone.id], 0)

    def test_score_calculation_logic(self):
        # Default settings: k_cd=4.0, b_cd=0.75, b_ud=0.25
        settings = ClickDistanceSettings(ranking_weight=0.1, k_cd=4.0, b_cd=0.75, b_ud=0.25)
        service = ClickDistanceService(settings=settings)

        # root: depth 0, url 0 -> blended 0.75 / 1.0 = 0.75
        # score = 4 / (4 + 0.75) = 0.842
        score, state, diags = service.calculate_score(scope_depth=0, url_depth=0)
        self.assertEqual(state, "computed")
        self.assertAlmostEqual(score, 0.842105, places=6)

        # deep: depth 4, url 4 -> blended (0.75*5 + 0.25*4) = 4.75
        # score = 4 / (4 + 4.75) = 0.45714...
        score2, _, _ = service.calculate_score(scope_depth=4, url_depth=4)
        self.assertLess(score2, score)
        self.assertAlmostEqual(score2, 0.457143, places=6)

    def test_recalculate_all_updates_content_items(self):
        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        ContentItem.objects.create(content_id=1, content_type="thread", title="P1", scope=scope, url="https://x.com/1")
        ContentItem.objects.create(content_id=2, content_type="thread", title="P2", scope=scope, url="https://x.com/a/b")

        service = ClickDistanceService()
        service.recalculate_all()

        p1 = ContentItem.objects.get(content_id=1)
        p2 = ContentItem.objects.get(content_id=2)
        self.assertGreater(p1.click_distance_score, 0.5)
        self.assertGreater(p1.click_distance_score, p2.click_distance_score)


class ClickDistanceRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=10, silo_group_id=None)
        # destination has click_distance_score (the field on ContentItem)
        # In ranker, it's passed via ContentRecord
        self.host = _content_record(content_id=20, silo_group_id=None)
        self.records = {self.destination.key: self.destination, self.host.key: self.host}
        self.weights = {"w_semantic": 0.5, "w_keyword": 0.5, "w_node": 0, "w_quality": 0}
        self.bounds = (0.1, 2.0)

    def test_click_distance_weight_zero_has_no_effect(self):
        dest_neutral = _content_record(content_id=10, silo_group_id=None)
        # click_distance_score defaults to 0.0 in _content_record but 0.5 means neutral in ranker
        
        matches = [SentenceSemanticMatch(20, "thread", 20, 0.8)]
        sentence_records = {20: SentenceRecord(20, 20, "thread", "test", 80, frozenset())}

        baseline = score_destination_matches(
            dest_neutral,
            matches,
            content_records=self.records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            click_distance_ranking_weight=0.0,
        )[0]
        
        enabled = score_destination_matches(
            dest_neutral,
            matches,
            content_records=self.records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            click_distance_ranking_weight=0.2,
        )[0]

        self.assertAlmostEqual(baseline.score_final, enabled.score_final, places=6)

    def test_click_distance_score_boosts_final_score(self):
        # Use dataclasses.replace instead of __dict__ for slotted dataclasses
        dest_shallow = replace(self.destination, click_distance_score=0.9)
        dest_deep = replace(self.destination, click_distance_score=0.3)
        
        matches = [SentenceSemanticMatch(20, "thread", 20, 0.8)]
        sentence_records = {20: SentenceRecord(20, 20, "thread", "test", 80, frozenset())}
        
        shallow_result = score_destination_matches(
            dest_shallow,
            matches,
            content_records={dest_shallow.key: dest_shallow, self.host.key: self.host},
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            click_distance_ranking_weight=0.2,
        )[0]
        
        deep_result = score_destination_matches(
            dest_deep,
            matches,
            content_records={dest_deep.key: dest_deep, self.host.key: self.host},
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            click_distance_ranking_weight=0.2,
        )[0]

        # score factor = 2 * (score - 0.5)
        # shallow: 2 * (0.9 - 0.5) = 0.8 bonus
        # deep: 2 * (0.3 - 0.5) = -0.4 penalty
        self.assertGreater(shallow_result.score_final, deep_result.score_final)
        self.assertAlmostEqual(shallow_result.score_click_distance, 0.9)
        self.assertAlmostEqual(shallow_result.score_click_distance, 0.9)
        self.assertAlmostEqual(deep_result.score_click_distance, 0.3)


class FeedbackRerankServiceTests(TestCase):
    def setUp(self):
        self.settings = FeedbackRerankSettings(
            enabled=True,
            ranking_weight=0.2,
            exploration_rate=1.0,
            alpha_prior=1.0,
            beta_prior=1.0
        )
        self.service = FeedbackRerankService(self.settings)

    def test_bayesian_smoothing_exploit_score(self):
        # 0/0 -> (0+1)/(0+1+1) = 0.5
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertEqual(diags["score_exploit"], 0.5)
        
        # 10/10 -> (10+1)/(10+2) = 11/12 = 0.9167
        self.service._pair_stats[(1, 1)] = {"total": 10, "successes": 10}
        self.service._global_total_samples = 10
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertAlmostEqual(diags["score_exploit"], 0.9167, places=4)

        # 0/10 -> (0+1)/(10+2) = 1/12 = 0.0833
        self.service._pair_stats[(1, 1)] = {"total": 10, "successes": 0}
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertAlmostEqual(diags["score_exploit"], 0.0833, places=4)

    def test_ucb1_explore_boost(self):
        # Global=100, Pair=0 -> sqrt(ln(101)/1) = 2.14k
        self.service._global_total_samples = 100
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertGreater(diags["score_explore"], 2.0)

        # Global=100, Pair=100 -> sqrt(ln(101)/101) = 0.21k
        self.service._pair_stats[(1, 1)] = {"total": 100, "successes": 50}
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertLess(diags["score_explore"], 0.3)

    def test_rerank_candidates_integration(self):
        from apps.pipeline.services.ranker import ScoredCandidate
        
        # Mock global stats: a lot of data for (1,1) with 100% success
        self.service._pair_stats[(1, 1)] = {"total": 100, "successes": 100}
        self.service._global_total_samples = 100
        
        candidates = [
            ScoredCandidate(
                destination_content_id=1, destination_content_type="thread",
                host_content_id=2, host_content_type="thread",
                host_sentence_id=1,
                score_semantic=0.8, score_keyword=0.2, score_node_affinity=0.1,
                score_quality=0.5, score_silo_affinity=0.0,
                score_phrase_relevance=0.5, score_learned_anchor_corroboration=0.5,
                score_rare_term_propagation=0.5, score_field_aware_relevance=0.5,
                score_ga4_gsc=0.5, score_click_distance=0.5,
                score_explore_exploit=0.0,
                score_cluster_suppression=0.0, # Added missing field
                score_final=1.0,
                anchor_phrase="test", anchor_start=0, anchor_end=4, anchor_confidence="strong",
                phrase_match_diagnostics={}, learned_anchor_diagnostics={},
                rare_term_diagnostics={}, field_aware_diagnostics={},
                cluster_diagnostics={}, # Added missing field
                explore_exploit_diagnostics={},
                click_distance_diagnostics={}
            )
        ]
        
        # host_id=2 maps to scope=1, dest_id=1 maps to scope=1
        reranked = self.service.rerank_candidates(
            candidates,
            host_scope_id_map={2: 1},
            destination_scope_id_map={1: 1}
        )
        
        # Factor should be > 1.0 because of high success rate
        self.assertGreater(reranked[0].score_final, 1.0)
        self.assertGreater(reranked[0].score_explore_exploit, 1.0)
        self.assertIn("score_exploit", reranked[0].explore_exploit_diagnostics)
