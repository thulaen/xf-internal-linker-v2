from django.test import TestCase

from apps.content.models import ContentItem, ScopeItem, SiloGroup
from apps.pipeline.services.pipeline import _persist_diagnostics
from apps.pipeline.services.ranker import (
    ContentRecord,
    SentenceRecord,
    SentenceSemanticMatch,
    SiloSettings,
    score_destination_matches,
)
from apps.suggestions.models import PipelineDiagnostic, PipelineRun


def _content_record(*, content_id: int, silo_group_id: int | None) -> ContentRecord:
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
        pagerank_score=1.0,
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
        self.pagerank_bounds = (0.5, 2.0)

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
            pagerank_bounds=self.pagerank_bounds,
            silo_settings=SiloSettings(mode="disabled"),
        )[0]
        disabled_cross = score_destination_matches(
            self.destination,
            cross_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            pagerank_bounds=self.pagerank_bounds,
            silo_settings=SiloSettings(mode="disabled"),
        )[0]
        preferred_same = score_destination_matches(
            self.destination,
            same_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            pagerank_bounds=self.pagerank_bounds,
            silo_settings=SiloSettings(mode="prefer_same_silo", same_silo_boost=0.2, cross_silo_penalty=0.1),
        )[0]
        preferred_cross = score_destination_matches(
            self.destination,
            cross_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            pagerank_bounds=self.pagerank_bounds,
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
            pagerank_bounds=self.pagerank_bounds,
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
            pagerank_bounds=self.pagerank_bounds,
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
