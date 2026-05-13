from django.test import SimpleTestCase

from apps.pipeline.services import ranker
from apps.pipeline.services.ranker_types import (
    ClusteringSettings,
    ContentRecord,
    ScoredCandidate,
    SentenceRecord,
    SentenceSemanticMatch,
    SiloSettings,
)


class RankerTypesTests(SimpleTestCase):
    def test_ranker_reexports_record_types(self) -> None:
        self.assertIs(ranker.ContentRecord, ContentRecord)
        self.assertIs(ranker.ScoredCandidate, ScoredCandidate)
        self.assertIs(ranker.SiloSettings, SiloSettings)

    def test_record_key_helpers_return_content_keys(self) -> None:
        content = ContentRecord(
            content_id=10,
            content_type="thread",
            title="Title",
            distilled_text="Useful text",
            scope_id=1,
            scope_type="node",
            parent_id=None,
            parent_type="",
            grandparent_id=None,
            grandparent_type="",
            silo_group_id=None,
            silo_group_name="",
            reply_count=0,
            march_2026_pagerank_score=0.0,
            link_freshness_score=0.5,
            primary_post_char_count=100,
            tokens=frozenset({"useful"}),
        )
        sentence = SentenceRecord(
            sentence_id=20,
            content_id=10,
            content_type="thread",
            text="Useful text.",
            char_count=12,
            tokens=frozenset({"useful"}),
        )
        match = SentenceSemanticMatch(
            host_content_id=10,
            host_content_type="thread",
            sentence_id=20,
            score_semantic=0.8,
        )

        self.assertEqual(content.key, (10, "thread"))
        self.assertEqual(sentence.content_key, (10, "thread"))
        self.assertEqual(match.host_key, (10, "thread"))

    def test_defaults_stay_neutral_after_type_split(self) -> None:
        self.assertEqual(ClusteringSettings().similarity_threshold, 0.04)
        self.assertEqual(SiloSettings().mode, "prefer_same_silo")
