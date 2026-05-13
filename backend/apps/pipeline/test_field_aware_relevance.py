"""Focused tests for early main-content relevance diagnostics."""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.pipeline.services import field_aware_relevance as service
from apps.pipeline.services.field_aware_relevance import (
    FieldAwareRelevanceSettings,
    evaluate_field_aware_relevance,
)
from apps.pipeline.services.learned_anchor import LearnedAnchorInputRow
from apps.pipeline.services.ranker import ContentRecord


def _record(
    *,
    content_id: int,
    title: str,
    distilled_text: str,
    tokens: frozenset[str],
    headings: list[str] | None = None,
    scope_title: str = "",
    parent_scope_title: str = "",
    grandparent_scope_title: str = "",
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
        parent_scope_title=parent_scope_title,
        grandparent_scope_title=grandparent_scope_title,
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


class FieldAwareRelevanceMutationGuardTests(SimpleTestCase):
    def test_component_is_centered_and_clamped(self) -> None:
        self.assertEqual(service.score_field_aware_component(0.0), 0.0)
        self.assertEqual(service.score_field_aware_component(0.5), 0.0)
        self.assertAlmostEqual(service.score_field_aware_component(0.75), 0.5)
        self.assertEqual(service.score_field_aware_component(1.0), 1.0)
        self.assertEqual(service.score_field_aware_component(2.0), 1.0)

    def test_empty_destination_returns_neutral_no_destination_terms(self) -> None:
        destination = _record(
            content_id=704,
            title="",
            distilled_text="",
            tokens=frozenset(),
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="known terms",
            inbound_anchor_rows=[],
            settings=FieldAwareRelevanceSettings(),
        )

        self.assertEqual(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_component, 0.0)
        self.assertEqual(result.field_aware_state, "neutral_no_destination_terms")
        self.assertEqual(result.field_aware_diagnostics["matched_field_count"], 0)
        self.assertEqual(
            result.field_aware_diagnostics["field_lengths"],
            {
                "title": 0,
                "heading": 0,
                "intro": 0,
                "body": 0,
                "scope": 0,
                "learned_anchor": 0,
            },
        )

    def test_empty_host_returns_neutral_no_host_terms(self) -> None:
        destination = _record(
            content_id=705,
            title="Internal Linking Guide",
            distilled_text="guide content",
            tokens=frozenset({"internal", "linking", "guide"}),
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="the and for",
            inbound_anchor_rows=[],
            settings=FieldAwareRelevanceSettings(),
        )

        self.assertEqual(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_component, 0.0)
        self.assertEqual(result.field_aware_state, "neutral_no_host_terms")
        self.assertEqual(
            result.field_aware_diagnostics["field_lengths"]["title"],
            3,
        )
        self.assertIn("title", result.field_aware_diagnostics["field_scores"])

    def test_neutral_result_contains_complete_diagnostics(self) -> None:
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 2}),
            field_length=2,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        result = service._neutral_result(
            field_aware_state="neutral_test",
            settings=FieldAwareRelevanceSettings(title_field_weight=0.4),
            field_profiles=(profile,),
        )

        self.assertEqual(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_component, 0.0)
        self.assertEqual(result.field_aware_state, "neutral_test")
        self.assertEqual(
            result.field_aware_diagnostics["score_field_aware_relevance"],
            0.5,
        )
        self.assertEqual(
            result.field_aware_diagnostics["field_aware_state"],
            "neutral_test",
        )
        self.assertEqual(result.field_aware_diagnostics["field_weights"]["title"], 0.4)
        self.assertEqual(result.field_aware_diagnostics["field_lengths"]["title"], 2)

    def test_field_profiles_split_all_configured_fields(self) -> None:
        destination = _record(
            content_id=706,
            title="Internal Linking Guide",
            distilled_text=" ".join(["intro"] * 80 + ["body", "terms"]),
            tokens=frozenset({"internal", "linking", "guide", "body", "terms"}),
            headings=["Editor Workflow"],
            scope_title="Guides",
        )

        profiles = service._build_field_profiles(
            destination=destination,
            inbound_anchor_rows=[
                LearnedAnchorInputRow(source_content_id=1, anchor_text="Guide Anchor"),
                LearnedAnchorInputRow(source_content_id=2, anchor_text="click here"),
            ],
            settings=FieldAwareRelevanceSettings(),
        )

        by_name = {profile.name: profile for profile in profiles}
        self.assertEqual(
            tuple(by_name),
            ("title", "heading", "intro", "body", "scope", "learned_anchor"),
        )
        self.assertEqual(by_name["title"].token_counts["internal"], 1)
        self.assertEqual(by_name["heading"].token_counts["editor"], 1)
        self.assertEqual(by_name["intro"].field_length, 80)
        self.assertEqual(by_name["body"].token_counts["body"], 1)
        self.assertEqual(by_name["scope"].token_counts["guides"], 1)
        self.assertEqual(by_name["learned_anchor"].token_counts["guide"], 1)
        self.assertNotIn("click", by_name["learned_anchor"].token_counts)

    def test_field_presence_counts_each_field_once_per_token(self) -> None:
        profiles = (
            service._FieldProfile(
                name="title",
                token_counts=Counter({"guide": 2, "workflow": 1}),
                field_length=3,
                field_weight=0.3,
                b_value=service.TITLE_B,
            ),
            service._FieldProfile(
                name="body",
                token_counts=Counter({"guide": 1, "body": 1}),
                field_length=2,
                field_weight=0.15,
                b_value=service.BODY_B,
            ),
        )

        counts = service._build_field_presence_count(profiles)

        self.assertEqual(counts, Counter({"guide": 2, "workflow": 1, "body": 1}))

    def test_score_field_rejects_empty_profiles_and_sorts_top_terms(self) -> None:
        empty_profile = service._FieldProfile(
            name="title",
            token_counts=Counter(),
            field_length=0,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )
        self.assertEqual(
            service._score_field(
                profile=empty_profile,
                host_token_counts=Counter({"guide": 1}),
                field_presence_count=Counter({"guide": 1}),
            ),
            (0.0, []),
        )

        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 3, "workflow": 1}),
            field_length=4,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )
        with patch.object(service, "HAS_CPP_EXT", False):
            score, terms = service._score_field(
                profile=profile,
                host_token_counts=Counter({"guide": 2, "workflow": 1}),
                field_presence_count=Counter({"guide": 1, "workflow": 3}),
            )

        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)
        self.assertEqual([term["token"] for term in terms], ["guide", "workflow"])
        self.assertEqual(terms[0]["field_tf"], 3)
        self.assertEqual(terms[0]["host_tf"], 2)
        self.assertEqual(terms[0]["field_presence_count"], 1)

    def test_score_field_rejects_zero_length_even_with_counts(self) -> None:
        inconsistent_profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1}),
            field_length=0,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        self.assertEqual(
            service._score_field(
                profile=inconsistent_profile,
                host_token_counts=Counter({"guide": 1}),
                field_presence_count=Counter({"guide": 1}),
            ),
            (0.0, []),
        )

    def test_score_field_ignores_host_terms_missing_from_field(self) -> None:
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1}),
            field_length=1,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        self.assertEqual(
            service._score_field(
                profile=profile,
                host_token_counts=Counter({"absent": 1}),
                field_presence_count=Counter({"guide": 1}),
            ),
            (0.0, []),
        )

    def test_no_matching_fields_returns_neutral_no_field_matches(self) -> None:
        destination = _record(
            content_id=708,
            title="Internal Linking Guide",
            distilled_text="guide content",
            tokens=frozenset({"internal", "linking", "guide"}),
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="canonical tags only",
            inbound_anchor_rows=[],
            settings=FieldAwareRelevanceSettings(),
        )

        self.assertEqual(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_component, 0.0)
        self.assertEqual(result.field_aware_state, "neutral_no_field_matches")
        self.assertGreater(
            result.field_aware_diagnostics["field_lengths"]["title"],
            0,
        )
        self.assertEqual(
            result.field_aware_diagnostics["field_scores"]["title"]["matched_terms"],
            [],
        )

    def test_score_field_python_fallback_matches_exact_formula(self) -> None:
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 3}),
            field_length=3,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        with patch.object(service, "HAS_CPP_EXT", False):
            score, terms = service._score_field(
                profile=profile,
                host_token_counts=Counter({"guide": 2}),
                field_presence_count=Counter({"guide": 1}),
            )

        expected_raw = terms[0]["token_score"]
        self.assertAlmostEqual(score, expected_raw / (1.0 + expected_raw), places=6)
        expected_idf = round(
            service.math.log1p(
                (1.0 + service.FIELD_COUNT) / (1.0 + float(1))
            ),
            6,
        )
        self.assertEqual(terms[0]["idf"], expected_idf)

    def test_score_field_cpp_extension_branch_uses_exact_arguments(self) -> None:
        calls = []

        def fake_score_field_tokens(*args):
            calls.append(args)
            return 0.25

        fake_fieldrel = SimpleNamespace(score_field_tokens=fake_score_field_tokens)
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 2}),
            field_length=2,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        with (
            patch.object(service, "HAS_CPP_EXT", True),
            patch.object(service, "fieldrel", fake_fieldrel, create=True),
        ):
            score, terms = service._score_field(
                profile=profile,
                host_token_counts=Counter({"guide": 1}),
                field_presence_count=Counter({"guide": 1}),
            )

        self.assertIsInstance(score, float)
        self.assertEqual(score, 0.25)
        self.assertEqual(terms[0]["token"], "guide")
        self.assertEqual(
            calls,
            [
                (
                    ["guide"],
                    [1],
                    [2],
                    [1],
                    2,
                    service.REFERENCE_FIELD_LENGTHS["title"],
                    service.TITLE_B,
                    service.FIELD_COUNT,
                    service.BM25_K1,
                    service.MAX_MATCHED_TOKENS_PER_FIELD,
                )
            ],
        )

    def test_public_wrapper_returns_neutral_processing_error_on_exception(self) -> None:
        destination = _record(
            content_id=707,
            title="Internal Linking Guide",
            distilled_text="guide content",
            tokens=frozenset({"internal", "linking", "guide"}),
        )

        with patch.object(
            service,
            "_evaluate_field_aware_relevance",
            side_effect=ValueError("broken scoring"),
        ):
            result = evaluate_field_aware_relevance(
                destination=destination,
                host_sentence_text="internal guide",
                inbound_anchor_rows=[],
                settings=FieldAwareRelevanceSettings(),
            )

        self.assertEqual(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_component, 0.0)
        self.assertEqual(result.field_aware_state, "neutral_processing_error")

    def test_diagnostics_round_score_to_six_decimal_places(self) -> None:
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1}),
            field_length=1,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )
        matched_terms = [{"token": "guide", "token_score": 0.7}]
        diagnostics = service._build_diagnostics(
            field_aware_state="computed_match",
            settings=FieldAwareRelevanceSettings(
                title_field_weight=0.1234564,
                heading_field_weight=0.2345674,
                intro_field_weight=0.3456784,
                body_field_weight=0.4567894,
                scope_field_weight=0.5678914,
                learned_anchor_field_weight=0.6789124,
            ),
            field_profiles=(profile,),
            matched_fields=[(profile, 0.9876544, matched_terms)],
            score=0.1234564,
        )

        self.assertEqual(diagnostics["score_field_aware_relevance"], 0.123456)
        self.assertEqual(
            diagnostics["field_weights"],
            {
                "title": 0.123456,
                "heading": 0.234567,
                "intro": 0.345678,
                "body": 0.456789,
                "scope": 0.567891,
                "learned_anchor": 0.678912,
            },
        )
        self.assertEqual(diagnostics["matched_field_count"], 1)
        self.assertTrue(diagnostics["matched_early_main_content"])
        self.assertEqual(diagnostics["matched_early_fields"], ["title"])
        self.assertEqual(
            diagnostics["field_scores"]["title"],
            {"score": 0.987654, "matched_terms": matched_terms},
        )

    def test_bm25_tf_norm_uses_field_length_normalization(self) -> None:
        score = service._bm25_tf_norm(
            term_frequency=3,
            field_length=16,
            reference_length=8.0,
            b_value=0.25,
        )

        expected_denominator = 3.0 + service.BM25_K1 * (1.0 - 0.25 + 0.25 * 2.0)
        expected = (3.0 * (service.BM25_K1 + 1.0)) / expected_denominator
        self.assertAlmostEqual(score, expected, places=12)

    def test_score_field_tie_breaks_by_higher_field_frequency(self) -> None:
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"alpha": 1, "beta": 3}),
            field_length=4,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        with (
            patch.object(service, "HAS_CPP_EXT", False),
            patch.object(service, "_bm25_tf_norm", return_value=1.0),
        ):
            _score, terms = service._score_field(
                profile=profile,
                host_token_counts=Counter({"alpha": 1, "beta": 1}),
                field_presence_count=Counter({"alpha": 1, "beta": 1}),
            )

        self.assertEqual([term["token"] for term in terms], ["beta", "alpha"])

    def test_text_helpers_cover_missing_and_structured_values(self) -> None:
        self.assertEqual(service._heading_text(None), "")
        self.assertEqual(service._heading_text({}), "")
        self.assertEqual(service._heading_text({"headings": "Main Heading"}), "Main Heading")
        self.assertEqual(
            service._heading_text({"heading_text": ["One", None, "Two"]}),
            "One Two",
        )
        self.assertEqual(
            service._heading_text({"h1": "Main", "h2": ["Sub", ""], "h3": 42}),
            "Main Sub",
        )
        self.assertEqual(
            service._heading_text({"h1": "Main", "h2": ["Sub"], "h3": "Third"}),
            "Main Sub Third",
        )
        self.assertEqual(
            service._learned_anchor_text(
                [
                    LearnedAnchorInputRow(source_content_id=1, anchor_text=None),
                    LearnedAnchorInputRow(source_content_id=2, anchor_text=""),
                    LearnedAnchorInputRow(source_content_id=3, anchor_text="read more"),
                    LearnedAnchorInputRow(source_content_id=4, anchor_text=" Deep Guide "),
                ]
            ),
            "Deep Guide",
        )
        self.assertEqual(
            service._learned_anchor_text(
                [
                    LearnedAnchorInputRow(source_content_id=1, anchor_text="First"),
                    LearnedAnchorInputRow(source_content_id=2, anchor_text="Second"),
                ]
            ),
            "First Second",
        )
        self.assertEqual(
            service._token_counts("The Guide guide, and WORKFLOW."),
            Counter({"guide": 2, "workflow": 1}),
        )
        self.assertEqual(service._normalize_noise_text(" Read   MORE! "), "read more")
        self.assertEqual(service._normalize_noise_text(None), "")

    def test_early_match_helpers_require_positive_early_scores(self) -> None:
        matched_by_name = {
            "title": (0.0, []),
            "heading": (0.3, [{"token": "guide"}]),
            "body": (0.9, [{"token": "body"}]),
        }

        self.assertTrue(service._has_early_match(matched_by_name))
        self.assertEqual(service._matched_early_fields(matched_by_name), ["heading"])
        self.assertTrue(service._has_early_match({"intro": (0.2, [])}))
        self.assertEqual(service._matched_early_fields({"intro": (0.2, [])}), ["intro"])
        self.assertFalse(service._has_early_match({"body": (0.9, [])}))
        self.assertEqual(service._matched_early_fields({"body": (0.9, [])}), [])

    def test_combined_score_uses_active_field_weights_only(self) -> None:
        destination = _record(
            content_id=709,
            title="Guide",
            distilled_text="guide " + "intro " * 80 + "body guide",
            tokens=frozenset({"guide", "intro", "body"}),
            headings=["Guide"],
        )
        settings = FieldAwareRelevanceSettings(
            title_field_weight=0.6,
            heading_field_weight=0.2,
            intro_field_weight=0.0,
            body_field_weight=0.2,
            scope_field_weight=0.0,
            learned_anchor_field_weight=0.0,
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="guide",
            inbound_anchor_rows=[],
            settings=settings,
        )

        self.assertEqual(result.field_aware_state, "computed_match")
        self.assertGreater(result.score_field_aware_relevance, 0.5)
        self.assertLessEqual(result.score_field_aware_relevance, 1.0)
        self.assertEqual(
            result.field_aware_diagnostics["matched_early_fields"],
            ["title", "heading", "intro"],
        )

    def test_combined_score_uses_exact_weighted_average(self) -> None:
        destination = _record(
            content_id=712,
            title="Guide",
            distilled_text="Body",
            tokens=frozenset({"guide", "body"}),
        )
        title_profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1}),
            field_length=1,
            field_weight=0.2,
            b_value=service.TITLE_B,
        )
        body_profile = service._FieldProfile(
            name="body",
            token_counts=Counter({"body": 1}),
            field_length=1,
            field_weight=0.3,
            b_value=service.BODY_B,
        )

        with (
            patch.object(
                service,
                "_build_field_profiles",
                return_value=(title_profile, body_profile),
            ),
            patch.object(
                service,
                "_score_field",
                side_effect=[
                    (0.2, [{"token": "guide"}]),
                    (0.8, [{"token": "body"}]),
                ],
            ),
        ):
            result = evaluate_field_aware_relevance(
                destination=destination,
                host_sentence_text="guide body",
                inbound_anchor_rows=[],
                settings=FieldAwareRelevanceSettings(),
            )

        self.assertEqual(result.field_aware_state, "computed_match")
        self.assertEqual(result.field_aware_diagnostics["field_aware_state"], "computed_match")
        self.assertAlmostEqual(result.score_field_aware_relevance, 0.78)
        self.assertAlmostEqual(result.field_aware_component, 0.56)

    def test_combined_score_is_clamped_to_one_before_centering(self) -> None:
        destination = _record(
            content_id=713,
            title="Guide",
            distilled_text="",
            tokens=frozenset({"guide"}),
        )
        title_profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1}),
            field_length=1,
            field_weight=0.5,
            b_value=service.TITLE_B,
        )

        with (
            patch.object(service, "_build_field_profiles", return_value=(title_profile,)),
            patch.object(
                service,
                "_score_field",
                return_value=(2.0, [{"token": "guide"}]),
            ),
        ):
            result = evaluate_field_aware_relevance(
                destination=destination,
                host_sentence_text="guide",
                inbound_anchor_rows=[],
                settings=FieldAwareRelevanceSettings(),
            )

        self.assertEqual(result.score_field_aware_relevance, 1.0)
        self.assertEqual(result.field_aware_component, 1.0)

    def test_combined_score_stays_neutral_when_matched_weights_are_zero(self) -> None:
        destination = _record(
            content_id=710,
            title="Guide",
            distilled_text="",
            tokens=frozenset({"guide"}),
        )
        settings = FieldAwareRelevanceSettings(
            title_field_weight=0.0,
            heading_field_weight=0.0,
            intro_field_weight=0.0,
            body_field_weight=0.0,
            scope_field_weight=0.0,
            learned_anchor_field_weight=0.0,
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="guide",
            inbound_anchor_rows=[],
            settings=settings,
        )

        self.assertEqual(result.field_aware_state, "computed_match")
        self.assertEqual(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_component, 0.0)

    def test_scope_profile_joins_scope_levels_with_single_spaces(self) -> None:
        destination = _record(
            content_id=711,
            title="",
            distilled_text="",
            tokens=frozenset(),
            scope_title="Child",
            parent_scope_title="Parent",
            grandparent_scope_title="Root",
        )

        profiles = service._build_field_profiles(
            destination=destination,
            inbound_anchor_rows=[],
            settings=FieldAwareRelevanceSettings(),
        )
        scope_profile = {profile.name: profile for profile in profiles}["scope"]
        anchor_profile = {profile.name: profile for profile in profiles}["learned_anchor"]

        self.assertEqual(scope_profile.token_counts, Counter({"child": 1, "parent": 1, "root": 1}))
        self.assertEqual(scope_profile.b_value, service.SCOPE_B)
        self.assertEqual(anchor_profile.b_value, service.LEARNED_ANCHOR_B)

    def test_score_field_uses_zero_default_for_missing_presence_counts(self) -> None:
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1}),
            field_length=1,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        with patch.object(service, "HAS_CPP_EXT", False):
            score, terms = service._score_field(
                profile=profile,
                host_token_counts=Counter({"guide": 2}),
                field_presence_count=Counter(),
            )

        raw_idf = service.math.log1p(1.0 + service.FIELD_COUNT)
        expected_idf = round(raw_idf, 6)
        expected_tf_norm = service._bm25_tf_norm(
            term_frequency=1,
            field_length=1,
            reference_length=service.REFERENCE_FIELD_LENGTHS["title"],
            b_value=service.TITLE_B,
        )
        expected_token_score = round(expected_tf_norm * raw_idf * 2.0, 6)
        self.assertGreater(score, 0.0)
        self.assertEqual(terms[0]["field_presence_count"], 0)
        self.assertEqual(terms[0]["idf"], expected_idf)
        self.assertEqual(terms[0]["token_score"], expected_token_score)

    def test_score_field_caps_host_term_frequency_at_two(self) -> None:
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1}),
            field_length=1,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        with patch.object(service, "HAS_CPP_EXT", False):
            score, terms = service._score_field(
                profile=profile,
                host_token_counts=Counter({"guide": 3}),
                field_presence_count=Counter({"guide": 1}),
            )

        raw_idf = service.math.log1p((1.0 + service.FIELD_COUNT) / 2.0)
        expected_tf_norm = service._bm25_tf_norm(
            term_frequency=1,
            field_length=1,
            reference_length=service.REFERENCE_FIELD_LENGTHS["title"],
            b_value=service.TITLE_B,
        )
        expected_token_score = round(expected_tf_norm * raw_idf * 2.0, 6)
        expected_score = expected_token_score / (1.0 + expected_token_score)
        self.assertAlmostEqual(score, expected_score, places=6)
        self.assertEqual(terms[0]["host_tf"], 3)
        self.assertEqual(terms[0]["token_score"], expected_token_score)

    def test_score_field_cpp_branch_uses_zero_default_presence_count(self) -> None:
        calls = []

        def fake_score_field_tokens(*args):
            calls.append(args)
            return 0.2

        fake_fieldrel = SimpleNamespace(score_field_tokens=fake_score_field_tokens)
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1}),
            field_length=1,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        with (
            patch.object(service, "HAS_CPP_EXT", True),
            patch.object(service, "fieldrel", fake_fieldrel, create=True),
        ):
            service._score_field(
                profile=profile,
                host_token_counts=Counter({"guide": 1}),
                field_presence_count=Counter(),
            )

        self.assertEqual(calls[0][3], [0])

    def test_score_field_python_fallback_averages_multiple_top_terms(self) -> None:
        profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1, "workflow": 1}),
            field_length=2,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )

        with patch.object(service, "HAS_CPP_EXT", False):
            score, terms = service._score_field(
                profile=profile,
                host_token_counts=Counter({"guide": 1, "workflow": 1}),
                field_presence_count=Counter({"guide": 1, "workflow": 1}),
            )

        expected_raw = sum(float(term["token_score"]) for term in terms) / len(terms)
        self.assertAlmostEqual(score, expected_raw / (1.0 + expected_raw), places=6)

    def test_bm25_tf_norm_uses_minimum_reference_length_of_one(self) -> None:
        score = service._bm25_tf_norm(
            term_frequency=1,
            field_length=2,
            reference_length=0.5,
            b_value=0.5,
        )

        expected_denominator = 1.0 + service.BM25_K1 * (1.0 - 0.5 + 0.5 * 2.0)
        expected = (service.BM25_K1 + 1.0) / expected_denominator
        self.assertAlmostEqual(score, expected, places=12)

    def test_bm25_tf_norm_handles_zero_and_one_denominators(self) -> None:
        self.assertEqual(
            service._bm25_tf_norm(
                term_frequency=0,
                field_length=0,
                reference_length=1.0,
                b_value=1.0,
            ),
            0.0,
        )
        self.assertEqual(
            service._bm25_tf_norm(
                term_frequency=1,
                field_length=0,
                reference_length=1.0,
                b_value=1.0,
            ),
            service.BM25_K1 + 1.0,
        )

    def test_diagnostics_default_unmatched_field_score_is_zero(self) -> None:
        title_profile = service._FieldProfile(
            name="title",
            token_counts=Counter({"guide": 1}),
            field_length=1,
            field_weight=0.3,
            b_value=service.TITLE_B,
        )
        body_profile = service._FieldProfile(
            name="body",
            token_counts=Counter({"body": 1}),
            field_length=1,
            field_weight=0.3,
            b_value=service.BODY_B,
        )

        diagnostics = service._build_diagnostics(
            field_aware_state="computed_match",
            settings=FieldAwareRelevanceSettings(),
            field_profiles=(title_profile, body_profile),
            matched_fields=[(title_profile, 0.4, [{"token": "guide"}])],
            score=0.7,
        )

        self.assertEqual(diagnostics["field_scores"]["body"]["score"], 0.0)
        self.assertEqual(diagnostics["field_scores"]["body"]["matched_terms"], [])
