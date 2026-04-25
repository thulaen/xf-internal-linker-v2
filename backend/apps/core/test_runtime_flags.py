"""Tests for ``apps.core.runtime_flags`` — cached AppSetting toggles.

Plus end-to-end tests that flipping a Phase 6 pick's ``*.enabled``
flag actually short-circuits the matching helper. These are the
"no-op toggle" regression tests called out in the senior-dev review.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase

from apps.core.runtime_flags import (
    DEFAULT_CACHE_TTL_SECONDS,
    invalidate,
    is_enabled,
)


class IsEnabledTests(TestCase):
    def setUp(self) -> None:
        # Each test starts with a clean cache so prior tests' values
        # don't bleed.
        cache.clear()

    def test_missing_row_returns_default(self) -> None:
        self.assertTrue(is_enabled("nonexistent.flag", default=True))
        self.assertFalse(is_enabled("nonexistent.flag", default=False))

    def test_persisted_true_returns_true(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="x.flag",
            defaults={"value": "true", "description": ""},
        )
        self.assertTrue(is_enabled("x.flag", default=False))

    def test_persisted_false_returns_false(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="x.flag",
            defaults={"value": "false", "description": ""},
        )
        # Default is True; row says false → must return False.
        self.assertFalse(is_enabled("x.flag", default=True))

    def test_string_variants_coerce(self) -> None:
        from apps.core.models import AppSetting

        for raw, expected in (
            ("yes", True),
            ("on", True),
            ("1", True),
            ("True", True),
            ("no", False),
            ("off", False),
            ("0", False),
            ("False", False),
        ):
            AppSetting.objects.update_or_create(
                key="x.flag", defaults={"value": raw, "description": ""}
            )
            invalidate("x.flag")  # purge cache so the new value reads
            self.assertEqual(
                is_enabled("x.flag", default=False),
                expected,
                f"{raw!r} should coerce to {expected}",
            )

    def test_invalidate_drops_cached_value(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="x.flag", defaults={"value": "true", "description": ""}
        )
        self.assertTrue(is_enabled("x.flag"))  # cache populated
        AppSetting.objects.update_or_create(
            key="x.flag", defaults={"value": "false", "description": ""}
        )
        # Without invalidate the cache still says True.
        self.assertTrue(is_enabled("x.flag"))
        # After invalidate the next read hits the DB and sees the new value.
        invalidate("x.flag")
        self.assertFalse(is_enabled("x.flag"))

    def test_zero_cache_seconds_bypasses_cache(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="x.flag", defaults={"value": "true", "description": ""}
        )
        self.assertTrue(is_enabled("x.flag", cache_seconds=0))
        AppSetting.objects.update_or_create(
            key="x.flag", defaults={"value": "false", "description": ""}
        )
        # No cache → next read hits DB immediately.
        self.assertFalse(is_enabled("x.flag", cache_seconds=0))

    def test_default_ttl_is_sane(self) -> None:
        # Sanity guard against future "let's drop the TTL" misedits.
        # 60 s is the documented value; <5 s would be hot-path-heavy,
        # >300 s would mean operator changes don't take effect for
        # ages.
        self.assertGreaterEqual(DEFAULT_CACHE_TTL_SECONDS, 5)
        self.assertLessEqual(DEFAULT_CACHE_TTL_SECONDS, 300)


class Phase6ToggleShortCircuitTests(TestCase):
    """Each Phase 6 helper consults its ``<pick>.enabled`` AppSetting
    flag. This regression suite proves that flipping the flag off
    short-circuits the helper, even when the underlying pip dep is
    installed.

    These are the regression tests called out in the senior-dev
    review (#2): without them, the Settings UI toggles are no-ops
    and operators have no way to disable a pick.
    """

    def setUp(self) -> None:
        cache.clear()

    def _set_flag(self, key: str, *, enabled: bool) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": "true" if enabled else "false",
                "description": "test toggle",
            },
        )
        invalidate(key)

    # ── apps.sources helpers ────────────────────────────────────

    def test_vader_sentiment_toggle_off_returns_neutral(self) -> None:
        from apps.sources import vader_sentiment

        if not vader_sentiment.HAS_VADER:
            self.skipTest("vaderSentiment not installed")
        # With toggle ON, a positive sentence has a positive compound
        # score (we just exercised this in test_phase6_helpers).
        self._set_flag("vader_sentiment.enabled", enabled=True)
        with_on = vader_sentiment.score("Wonderful, amazing day!")
        self.assertGreater(with_on.compound, 0.5)
        # Flipping the toggle off must short-circuit to NEUTRAL.
        self._set_flag("vader_sentiment.enabled", enabled=False)
        with_off = vader_sentiment.score("Wonderful, amazing day!")
        self.assertIs(with_off, vader_sentiment.NEUTRAL)

    def test_pysbd_toggle_off_falls_back_to_regex(self) -> None:
        from apps.sources import pysbd_segmenter

        if not pysbd_segmenter.HAS_PYSBD:
            self.skipTest("pysbd not installed")
        # With toggle ON, PySBD doesn't split on "Dr.".
        self._set_flag("pysbd_segmenter.enabled", enabled=True)
        with_on = pysbd_segmenter.split("I called Dr. Smith. He was busy.")
        self.assertEqual(len(with_on), 2)
        # With toggle OFF, the regex fallback splits on every "."
        # including the one in "Dr.".
        self._set_flag("pysbd_segmenter.enabled", enabled=False)
        with_off = pysbd_segmenter.split("I called Dr. Smith. He was busy.")
        self.assertEqual(len(with_off), 3)

    def test_yake_toggle_off_returns_empty(self) -> None:
        from apps.sources import yake_keywords

        if not yake_keywords.HAS_YAKE:
            self.skipTest("yake not installed")
        text = "Reciprocal rank fusion combines multiple ranked lists."
        self._set_flag("yake_keywords.enabled", enabled=True)
        self.assertGreater(len(yake_keywords.extract(text)), 0)
        self._set_flag("yake_keywords.enabled", enabled=False)
        self.assertEqual(yake_keywords.extract(text), [])

    def test_trafilatura_toggle_off_returns_none(self) -> None:
        from apps.sources import trafilatura_extractor

        if not trafilatura_extractor.HAS_TRAFILATURA:
            self.skipTest("trafilatura not installed")
        html = (
            "<html><body><article><p>Real body text here. "
            "Long enough for trafilatura to keep.</p></article>"
            "</body></html>"
        )
        self._set_flag("trafilatura_extractor.enabled", enabled=True)
        self.assertIsNotNone(trafilatura_extractor.extract(html))
        self._set_flag("trafilatura_extractor.enabled", enabled=False)
        self.assertIsNone(trafilatura_extractor.extract(html))

    def test_fasttext_toggle_off_returns_undefined(self) -> None:
        from apps.sources import fasttext_langid

        if not fasttext_langid.HAS_FASTTEXT:
            self.skipTest("fasttext not installed")
        # Cold-start the per-process model singleton.
        fasttext_langid._MODEL_SINGLETON = None
        fasttext_langid._MODEL_PATH_LOADED = None
        self._set_flag("fasttext_langid.enabled", enabled=False)
        result = fasttext_langid.predict("This is English text.")
        self.assertTrue(result.is_undefined)

    # ── apps.pipeline.services helpers ──────────────────────────

    def test_lda_toggle_off_returns_empty_distribution(self) -> None:
        from apps.pipeline.services import lda_topics

        self._set_flag("lda.enabled", enabled=False)
        result = lda_topics.infer_topics(["python", "tutorial"])
        self.assertIs(result, lda_topics.EMPTY_DISTRIBUTION)

    def test_kenlm_toggle_off_returns_neutral(self) -> None:
        from apps.pipeline.services import kenlm_fluency

        self._set_flag("kenlm.enabled", enabled=False)
        result = kenlm_fluency.score_fluency("The quick brown fox jumps.")
        self.assertEqual(result.log_prob, kenlm_fluency.NEUTRAL_SCORE)

    def test_node2vec_toggle_off_returns_none(self) -> None:
        from apps.pipeline.services import node2vec_embeddings

        self._set_flag("node2vec.enabled", enabled=False)
        self.assertIsNone(node2vec_embeddings.vector_for("any-node"))

    def test_bpr_toggle_off_returns_none(self) -> None:
        from apps.pipeline.services import bpr_ranking

        self._set_flag("bpr.enabled", enabled=False)
        result = bpr_ranking.score_for_user("u1", ["i1", "i2"])
        self.assertIsNone(result)

    def test_factorization_machines_toggle_off_returns_none(self) -> None:
        from apps.pipeline.services import factorization_machines

        self._set_flag("factorization_machines.enabled", enabled=False)
        result = factorization_machines.predict([{"a": 1.0}])
        self.assertIsNone(result)
