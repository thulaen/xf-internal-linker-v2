import math
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.content.models import ContentItem, ScopeItem, SiloGroup
from apps.core.models import AppSetting
from apps.graph.models import ExistingLink
from apps.pipeline.services.link_freshness import (
    LinkFreshnessPeerRow,
    LinkFreshnessSettings,
    calculate_link_freshness,
    run_link_freshness,
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
