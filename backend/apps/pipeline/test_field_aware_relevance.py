"""Focused tests for early main-content relevance diagnostics."""

from django.test import SimpleTestCase

from apps.pipeline.services.field_aware_relevance import (
    FieldAwareRelevanceSettings,
    evaluate_field_aware_relevance,
)
from apps.pipeline.services.ranker import ContentRecord


def _record(
    *,
    content_id: int,
    title: str,
    distilled_text: str,
    tokens: frozenset[str],
    headings: list[str] | None = None,
    scope_title: str = "",
) -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        content_type="thread",
        title=title,
        distilled_text=distilled_text,
        scope_id=10,
        scope_type="node",
        parent_id=None,
        parent_type="",
        grandparent_id=None,
        grandparent_type="",
        silo_group_id=None,
        silo_group_name="",
        reply_count=5,
        march_2026_pagerank_score=0.2,
        link_freshness_score=0.5,
        primary_post_char_count=500,
        tokens=tokens,
        scope_title=scope_title,
        nlp_metadata={"headings": headings or []},
    )


class FieldAwareRelevanceEarlyContentTests(SimpleTestCase):
    def test_heading_intro_and_title_matches_are_marked_early(self):
        destination = _record(
            content_id=701,
            title="Internal Linking Guide",
            distilled_text=" ".join(
                ["safe", "editor", "workflow"] + ["intro"] * 77 + ["internal", "links"]
            ),
            tokens=frozenset({"safe", "editor", "workflow", "internal", "links"}),
            headings=["Editor Workflow"],
            scope_title="Guides",
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="internal links editor workflow guides",
            inbound_anchor_rows=[],
            settings=FieldAwareRelevanceSettings(),
        )

        scores = result.field_aware_diagnostics["field_scores"]
        self.assertGreater(scores["title"]["score"], 0.0)
        self.assertGreater(scores["heading"]["score"], 0.0)
        self.assertGreater(scores["intro"]["score"], 0.0)
        self.assertGreater(scores["body"]["score"], 0.0)
        self.assertGreater(scores["scope"]["score"], 0.0)
        self.assertTrue(result.field_aware_diagnostics["matched_early_main_content"])
        self.assertEqual(
            result.field_aware_diagnostics["matched_early_fields"],
            ["title", "heading", "intro"],
        )

    def test_body_only_match_is_not_marked_early(self):
        destination = _record(
            content_id=702,
            title="General Advice",
            distilled_text=" ".join(["intro"] * 80 + ["advanced", "canonical"]),
            tokens=frozenset({"advanced", "canonical"}),
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="advanced canonical reference",
            inbound_anchor_rows=[],
            settings=FieldAwareRelevanceSettings(),
        )

        self.assertGreater(
            result.field_aware_diagnostics["field_scores"]["body"]["score"], 0.0
        )
        self.assertFalse(result.field_aware_diagnostics["matched_early_main_content"])
        self.assertEqual(result.field_aware_diagnostics["matched_early_fields"], [])

    def test_missing_heading_and_intro_stays_safe(self):
        destination = _record(
            content_id=703,
            title="Topic",
            distilled_text="",
            tokens=frozenset({"topic"}),
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="topic",
            inbound_anchor_rows=[],
            settings=FieldAwareRelevanceSettings(),
        )

        self.assertEqual(result.field_aware_state, "computed_match")
        self.assertIn("heading", result.field_aware_diagnostics["field_scores"])
        self.assertIn("intro", result.field_aware_diagnostics["field_scores"])
