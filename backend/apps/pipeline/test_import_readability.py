"""Integration test for pick #19 — Flesch-Kincaid + Gunning Fog readability wiring.

Proof point: when the importer's ``_persist_content_body`` runs on a
real ``clean_text``, the resulting Post row has non-zero
``flesch_kincaid_grade`` and ``gunning_fog_grade`` populated by
``apps.sources.readability.score``. Cold-start safe: empty / single-
word bodies persist 0.0 grades without raising.
"""

from __future__ import annotations

from django.test import TestCase

from apps.content.models import ContentItem, Post, ScopeItem
from apps.pipeline.tasks_import_helpers import _persist_content_body


class ReadabilityImportWiringTests(TestCase):
    def setUp(self) -> None:
        self.scope = ScopeItem.objects.create(
            scope_id=99,
            scope_type="node",
            title="readability-test",
        )
        self.content_item = ContentItem.objects.create(
            content_id=10_000,
            content_type="thread",
            title="Reading-grade fixture",
            scope=self.scope,
        )

    def test_complex_prose_persists_high_grade(self) -> None:
        """A passage of multi-syllable words yields a measurable grade."""
        # Sentences with several long words (Latinate vocabulary) push
        # Flesch-Kincaid + Fog up; the helper has been tested
        # independently, the proof here is that the importer wires it.
        clean = (
            "The implementation of comprehensive ontological frameworks "
            "necessitates considerable epistemological substantiation. "
            "Conventional methodologies frequently demonstrate inadequate "
            "differentiation between heterogeneous interpretations."
        )

        _persist_content_body(
            content_item=self.content_item,
            raw_body=clean,  # pretend the BBCode equals the cleaned form
            clean_text=clean,
            new_hash="hash_complex",
            first_post_id=None,
        )

        post = Post.objects.get(content_item=self.content_item)
        # Grades must be non-zero for non-trivial prose.
        self.assertGreater(post.flesch_kincaid_grade, 0.0)
        self.assertGreater(post.gunning_fog_grade, 0.0)
        # And the existing char/word counts still landed.
        self.assertGreater(post.char_count, 0)
        self.assertGreater(post.word_count, 0)

    def test_simple_prose_persists_low_grade(self) -> None:
        """A passage of short, single-syllable words yields a low grade."""
        clean = "The cat sat on the mat. The dog ran. The sun was hot."

        _persist_content_body(
            content_item=self.content_item,
            raw_body=clean,
            clean_text=clean,
            new_hash="hash_simple",
            first_post_id=None,
        )

        post = Post.objects.get(content_item=self.content_item)
        # Both grades exist (>= 0.0 since the helper rounds to 2 dp,
        # which can produce small negatives on degenerate inputs);
        # we assert presence of the wiring, not the exact number.
        self.assertIsNotNone(post.flesch_kincaid_grade)
        self.assertIsNotNone(post.gunning_fog_grade)
        # And complex prose should have higher grades than simple.
        # We re-run the test_complex_prose path within this test by
        # comparing the recorded simple grade to a known-complex
        # sentence run through the helper directly, to keep the
        # comparison hermetic.
        from apps.sources.readability import score as readability_score

        complex_grade = readability_score(
            "Implementation of comprehensive ontological frameworks "
            "necessitates considerable epistemological substantiation."
        )
        self.assertLess(post.flesch_kincaid_grade, complex_grade.flesch_kincaid_grade)

    def test_empty_clean_text_persists_zero_grades(self) -> None:
        """Cold-start / empty-body imports persist 0.0 grades, never raise."""
        _persist_content_body(
            content_item=self.content_item,
            raw_body="",
            clean_text="",
            new_hash="hash_empty",
            first_post_id=None,
        )

        post = Post.objects.get(content_item=self.content_item)
        self.assertEqual(post.flesch_kincaid_grade, 0.0)
        self.assertEqual(post.gunning_fog_grade, 0.0)
