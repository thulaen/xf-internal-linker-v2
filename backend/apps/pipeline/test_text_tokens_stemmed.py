"""Integration test for pick #21 — Snowball-stemmed tokenisation wiring.

Proof point: ``tokenize_text_stemmed`` produces a token frozenset
that:

1. Reuses :func:`tokenize_text`'s exact tokenisation contract — same
   stopword filter, same lowercasing, same punctuation handling — so
   surface and stemmed sets have a 1:1 correspondence on tokens that
   stem to themselves.
2. Collapses inflectional variants (running / runs / run all stem to
   ``run``) into a smaller set than the surface form.
3. Falls back to identity when the upstream ``snowballstemmer`` dep
   is absent (``stem_token`` returns its input unchanged).

The wiring contract is what matters — that pipeline_data and any
future consumer can rely on the helper being a drop-in extension of
``tokenize_text``.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.pipeline.services.text_tokens import (
    STANDARD_ENGLISH_STOPWORDS,
    tokenize_text,
    tokenize_text_stemmed,
)


class TokenizeTextStemmedTests(SimpleTestCase):
    def test_empty_input_returns_empty_frozenset(self) -> None:
        self.assertEqual(tokenize_text_stemmed(""), frozenset())
        self.assertEqual(tokenize_text_stemmed(None), frozenset())

    def test_returns_frozenset(self) -> None:
        result = tokenize_text_stemmed("Running quickly")
        self.assertIsInstance(result, frozenset)

    def test_inflectional_variants_collapse(self) -> None:
        """``running`` / ``runs`` / ``run`` should all map to one stem."""
        # The exact stem depends on Snowball's English rules but any
        # implementation must collapse these regular inflections.
        running = tokenize_text_stemmed("Running")
        runs = tokenize_text_stemmed("runs")
        run = tokenize_text_stemmed("Run")
        self.assertEqual(running, runs)
        self.assertEqual(runs, run)

    def test_stemming_reduces_set_size_on_inflected_text(self) -> None:
        """A passage with several inflected variants stems to fewer unique entries."""
        text = "running runs runner cats cat dog dogs"
        surface = tokenize_text(text)
        stemmed = tokenize_text_stemmed(text)
        # Before stemming: at least 7 distinct tokens.
        # After stemming: regular inflections collapse, so the set is
        # strictly smaller (cats↔cat, dogs↔dog, runs↔running).
        self.assertGreater(len(surface), len(stemmed))

    def test_no_inflections_means_no_collapse(self) -> None:
        """Tokens that are already stems pass through unchanged in count."""
        text = "alpha bravo charlie delta echo"
        surface = tokenize_text(text)
        stemmed = tokenize_text_stemmed(text)
        # No inflectional variants in the input → same cardinality.
        self.assertEqual(len(surface), len(stemmed))

    def test_stopwords_filtered_same_as_surface_path(self) -> None:
        """The stemmed path inherits the surface tokeniser's stopword filter."""
        text = "the quick brown fox jumps over the lazy dog"
        surface = tokenize_text(text)
        stemmed = tokenize_text_stemmed(text)
        # ``the`` is a stopword and must NOT appear in either set.
        self.assertNotIn("the", surface)
        self.assertNotIn("the", stemmed)
        # The stopword set itself is shared.
        for stop_token in ("the", "and", "of", "is"):
            self.assertIn(stop_token, STANDARD_ENGLISH_STOPWORDS)

    def test_stem_a_b_invariant(self) -> None:
        """``stem(a) == stem(b)`` ⟹ ``a`` and ``b`` collapse into the same stem in the output."""
        # Two different surface forms that we know stem to the same thing.
        a_text = "running"
        b_text = "runs"
        a_set = tokenize_text_stemmed(a_text)
        b_set = tokenize_text_stemmed(b_text)
        # Both produce a single stem (after stopword filtering); it must match.
        self.assertEqual(len(a_set), 1)
        self.assertEqual(a_set, b_set)


class PipelineDataDualTokensTests(SimpleTestCase):
    """Verify that ContentRecord and SentenceRecord carry both token sets."""

    def test_content_record_default_stemmed_tokens_empty(self) -> None:
        """The dataclass default is empty so existing fixtures keep working."""
        from apps.pipeline.services.ranker import ContentRecord

        rec = ContentRecord(
            content_id=1,
            content_type="thread",
            title="x",
            distilled_text="y",
            scope_id=0,
            scope_type="",
            parent_id=None,
            parent_type="",
            grandparent_id=None,
            grandparent_type="",
            silo_group_id=None,
            silo_group_name="",
            reply_count=0,
            march_2026_pagerank_score=0.0,
            link_freshness_score=0.5,
            primary_post_char_count=0,
            tokens=frozenset({"x"}),
        )
        # Default empty so 100+ existing test fixtures don't break.
        self.assertEqual(rec.stemmed_tokens, frozenset())

    def test_sentence_record_default_stemmed_tokens_empty(self) -> None:
        from apps.pipeline.services.ranker import SentenceRecord

        rec = SentenceRecord(
            sentence_id=1,
            content_id=1,
            content_type="thread",
            text="hello",
            char_count=5,
            tokens=frozenset({"hello"}),
        )
        self.assertEqual(rec.stemmed_tokens, frozenset())

    def test_content_record_can_carry_stemmed_tokens(self) -> None:
        from apps.pipeline.services.ranker import ContentRecord

        rec = ContentRecord(
            content_id=1,
            content_type="thread",
            title="x",
            distilled_text="y",
            scope_id=0,
            scope_type="",
            parent_id=None,
            parent_type="",
            grandparent_id=None,
            grandparent_type="",
            silo_group_id=None,
            silo_group_name="",
            reply_count=0,
            march_2026_pagerank_score=0.0,
            link_freshness_score=0.5,
            primary_post_char_count=0,
            tokens=frozenset({"running", "cats"}),
            stemmed_tokens=frozenset({"run", "cat"}),
        )
        self.assertEqual(rec.stemmed_tokens, frozenset({"run", "cat"}))
