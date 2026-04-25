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

    def test_no_model_path_configured_returns_undefined(self) -> None:
        """Even with the pip dep installed, missing AppSetting → UND."""
        # Default AppSetting has no row → path is empty → undefined.
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
        result = fasttext_langid.predict("Hello world")
        self.assertTrue(result.is_undefined)
