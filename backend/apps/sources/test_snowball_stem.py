"""Tests for pick #21 — Snowball / Porter2 stemmer wrapper."""

from __future__ import annotations

from unittest import skipUnless

from django.test import SimpleTestCase

from apps.sources import snowball_stem


# Pre-flight check so tests gracefully skip in containers that don't
# have ``snowballstemmer`` (e.g. an older image built before the
# requirements bump landed). The fallback identity behaviour is itself
# covered by the dedicated SnowballAvailability tests below.
HAS_SNOWBALL = snowball_stem.is_available()


class StemTokenTests(SimpleTestCase):
    @skipUnless(HAS_SNOWBALL, "snowballstemmer not installed in this container")
    def test_basic_inflection_collapses_to_stem(self) -> None:
        # Regular-verb inflections should collapse to one stem. Note we
        # don't assert on irregular verbs ("ran"), since Porter2 is a
        # rule-based stemmer, not a lemmatiser — it leaves "ran"
        # unchanged. That's an accepted IR limitation.
        self.assertEqual(
            snowball_stem.stem_token("running"), snowball_stem.stem_token("runs")
        )
        self.assertEqual(
            snowball_stem.stem_token("running"), snowball_stem.stem_token("run")
        )
        # Plural collapse is the canonical use case for stem-based recall.
        self.assertEqual(
            snowball_stem.stem_token("cat"), snowball_stem.stem_token("cats")
        )

    @skipUnless(HAS_SNOWBALL, "snowballstemmer not installed in this container")
    def test_idempotent_on_fixed_point(self) -> None:
        # Stem-of-a-stem returning the same string is the idempotency
        # invariant a pipeline relies on when stemming both at index
        # time AND at query time. Pick a word that lands on a Porter2
        # fixed point — "running" → "run" → "run" is the classical case.
        # (Some inputs like "organisation" hit Porter2's known
        # over-stemming behaviour where "organis" still has suffixes
        # the algorithm strips on a second pass — that's a documented
        # limitation, not a bug; we only assert idempotency on stems
        # that have already reached a fixed point.)
        first = snowball_stem.stem_token("running")
        self.assertEqual(snowball_stem.stem_token(first), first)

    @skipUnless(HAS_SNOWBALL, "snowballstemmer not installed in this container")
    def test_case_insensitive(self) -> None:
        # The wrapper lower-cases before stemming so capitalisation
        # variants converge.
        self.assertEqual(
            snowball_stem.stem_token("Running"), snowball_stem.stem_token("running")
        )

    @skipUnless(HAS_SNOWBALL, "snowballstemmer not installed in this container")
    def test_known_porter2_examples(self) -> None:
        # Spot-check a handful of canonical Porter2 reductions verified
        # against the upstream snowballstemmer 3.0.1 implementation.
        # These are the textbook examples — if they regress something
        # is very wrong (e.g. wrong language, broken cache).
        self.assertEqual(snowball_stem.stem_token("agreed"), "agre")
        self.assertEqual(snowball_stem.stem_token("agreement"), "agreement")
        self.assertEqual(snowball_stem.stem_token("happy"), "happi")
        self.assertEqual(snowball_stem.stem_token("relativity"), "relat")
        self.assertEqual(snowball_stem.stem_token("running"), "run")
        self.assertEqual(snowball_stem.stem_token("fences"), "fenc")

    def test_empty_string_returns_empty(self) -> None:
        # The empty-string short-circuit fires before snowballstemmer
        # is loaded, so this works even when the dep isn't installed.
        self.assertEqual(snowball_stem.stem_token(""), "")


class StemTextTests(SimpleTestCase):
    @skipUnless(HAS_SNOWBALL, "snowballstemmer not installed in this container")
    def test_splits_and_stems_each_token(self) -> None:
        stems = snowball_stem.stem_text("Running, jumps and ran!")
        # Punctuation is stripped, words lower-cased, and each piece stemmed.
        self.assertEqual(stems, [
            snowball_stem.stem_token("running"),
            snowball_stem.stem_token("jumps"),
            snowball_stem.stem_token("and"),
            snowball_stem.stem_token("ran"),
        ])

    @skipUnless(HAS_SNOWBALL, "snowballstemmer not installed in this container")
    def test_collapses_morphological_variants_in_text(self) -> None:
        # Two phrases with the same content words in different
        # inflections should produce identical stem sets.
        a = set(snowball_stem.stem_text("The cat is jumping over fences."))
        b = set(snowball_stem.stem_text("The cats jumped over a fence."))
        # "the" and "a" are not necessarily collapsed but the content
        # words ("cat", "jump", "fence") should overlap.
        for content_word in ("cat", "jump", "fenc"):  # "fenc" is the Porter2 stem of fence/fences
            self.assertIn(content_word, a)
            self.assertIn(content_word, b)

    def test_empty_string_returns_empty_list(self) -> None:
        self.assertEqual(snowball_stem.stem_text(""), [])

    def test_none_treated_as_empty(self) -> None:
        # Defensive — callers shouldn't pass None but if they do the
        # helper returns [] instead of raising.
        self.assertEqual(snowball_stem.stem_text(None), [])

    @skipUnless(HAS_SNOWBALL, "snowballstemmer not installed in this container")
    def test_punctuation_only_input(self) -> None:
        # No alphanumeric runs → empty list.
        self.assertEqual(snowball_stem.stem_text("...!?,"), [])


class SnowballAvailabilityTests(SimpleTestCase):
    def test_is_available_returns_bool(self) -> None:
        # Whatever the answer is, it must be a bool — callers branch on it.
        self.assertIsInstance(snowball_stem.is_available(), bool)

    def test_unknown_language_falls_back_to_identity(self) -> None:
        # A bogus language name should not crash; helpers fall back to
        # identity so the caller still gets a string back.
        result = snowball_stem.stem_token("running", language="klingon")
        # Identity → input was lowered first then returned unchanged.
        self.assertEqual(result, "running")
