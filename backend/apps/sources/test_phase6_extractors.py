"""Phase 6.2 — Trafilatura (#7) + FastText LangID (#14) wrapper tests."""

from __future__ import annotations

import unittest

from django.test import SimpleTestCase, TestCase

from apps.sources import fasttext_langid, trafilatura_extractor


class TrafilaturaExtractorTests(SimpleTestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(trafilatura_extractor.is_available(), bool)

    def test_empty_html_returns_none(self) -> None:
        self.assertIsNone(trafilatura_extractor.extract(""))
        self.assertIsNone(trafilatura_extractor.extract("   "))

    def test_cold_start_when_dep_missing_returns_none(self) -> None:
        if not trafilatura_extractor.HAS_TRAFILATURA:
            self.assertIsNone(
                trafilatura_extractor.extract("<html><body>x</body></html>")
            )
        else:
            self.skipTest("trafilatura is installed — cold-start test n/a")

    @unittest.skipUnless(
        trafilatura_extractor.HAS_TRAFILATURA, "trafilatura not installed"
    )
    def test_extracts_body_from_real_html(self) -> None:
        html = """
        <html>
        <head><title>Sample Article</title></head>
        <body>
        <nav>Top navigation links</nav>
        <article>
            <h1>Sample Article</h1>
            <p>This is a sample article body. It should be the only
            text Trafilatura returns. The navigation chrome above
            and the footer below should be stripped automatically.</p>
        </article>
        <footer>Footer chrome to strip</footer>
        </body>
        </html>
        """
        result = trafilatura_extractor.extract(html, url="http://example.com/")
        self.assertIsNotNone(result)
        self.assertIn("sample article body", result.text.lower())
        # Nav and footer should not survive.
        self.assertNotIn("navigation links", result.text.lower())


class FastTextLangIdTests(TestCase):
    """TestCase (not Simple) so AppSetting reads work."""

    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(fasttext_langid.is_available(), bool)

    def test_empty_text_returns_undefined(self) -> None:
        result = fasttext_langid.predict("")
        self.assertIs(result, fasttext_langid.UNDEFINED)
        self.assertTrue(result.is_undefined)

    def test_undefined_singleton_shape(self) -> None:
        u = fasttext_langid.UNDEFINED
        self.assertEqual(u.language, fasttext_langid.UND_LANGUAGE)
        self.assertEqual(u.confidence, 0.0)
        self.assertTrue(u.is_undefined)

    def test_explicit_empty_model_path_returns_undefined(self) -> None:
        """When operator explicitly clears the AppSetting → UND."""
        from apps.core.models import AppSetting

        # Migration 0043 seeds a default path; clear it for this test.
        AppSetting.objects.update_or_create(
            key=fasttext_langid.KEY_MODEL_PATH,
            defaults={"value": "", "description": ""},
        )
        # Reset the per-process cache so the prior test doesn't bleed
        # state between tests.
        fasttext_langid._MODEL_SINGLETON = None
        fasttext_langid._MODEL_PATH_LOADED = None
        result = fasttext_langid.predict("Hello world this is English")
        self.assertTrue(result.is_undefined)

    def test_invalid_model_path_returns_undefined(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=fasttext_langid.KEY_MODEL_PATH,
            defaults={
                "value": "/tmp/does-not-exist/lid.176.bin",
                "description": "",
            },
        )
        # Reset the per-process cache so a prior load doesn't bleed
        # state between tests.
        fasttext_langid._MODEL_SINGLETON = None
        fasttext_langid._MODEL_PATH_LOADED = None
        result = fasttext_langid.predict("Hello world")
        self.assertTrue(result.is_undefined)

    @unittest.skipUnless(
        fasttext_langid.HAS_FASTTEXT and __import__("os").path.exists(
            "/opt/models/lid.176.bin"
        ),
        "fasttext + lid.176.bin both required",
    )
    def test_real_prediction_classifies_english(self) -> None:
        """Real-data integration: with the model file present, fastText
        classifies obvious English correctly with high confidence."""
        # Ensure we hit the real model — clear any stale cache + use
        # the migrated default path.
        fasttext_langid._MODEL_SINGLETON = None
        fasttext_langid._MODEL_PATH_LOADED = None
        result = fasttext_langid.predict(
            "The quick brown fox jumps over the lazy dog. "
            "This is unmistakably English text with multiple sentences."
        )
        # fastText's lid.176 emits ISO 639-1 codes (e.g. "en"); the
        # docstring on the helper says "ISO 639-3" but that was an
        # over-spec — the actual labels are 2-letter.
        self.assertEqual(result.language, "en")
        self.assertGreater(result.confidence, 0.9)
