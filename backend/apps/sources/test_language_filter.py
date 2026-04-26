"""Tests for the FastText-LangID candidate-pool filter."""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.sources import language_filter


class _FakeRecord:
    """Minimal stand-in for ``ContentRecord`` — only ``title`` is read."""

    def __init__(self, title: str) -> None:
        self.title = title


class IsEnglishColdStartTests(SimpleTestCase):
    def test_empty_text_returns_true(self) -> None:
        self.assertTrue(language_filter.is_english(""))
        self.assertTrue(language_filter.is_english("   "))

    def test_fasttext_unavailable_returns_true(self) -> None:
        with patch(
            "apps.sources.fasttext_langid.predict",
            side_effect=RuntimeError("simulated outage"),
        ):
            self.assertTrue(language_filter.is_english("anything"))


class IsEnglishHappyPathTests(SimpleTestCase):
    def test_english_prediction_returns_true(self) -> None:
        from apps.sources.fasttext_langid import LangPrediction

        with patch(
            "apps.sources.fasttext_langid.predict",
            return_value=LangPrediction(language="en", confidence=0.99),
        ):
            self.assertTrue(language_filter.is_english("Hello world"))

    def test_undefined_prediction_returns_true(self) -> None:
        from apps.sources.fasttext_langid import UNDEFINED

        with patch(
            "apps.sources.fasttext_langid.predict",
            return_value=UNDEFINED,
        ):
            # ``und`` falls back to "allow" — better to keep the row
            # than drop it on a low-confidence prediction.
            self.assertTrue(language_filter.is_english("???"))

    def test_non_english_prediction_returns_false(self) -> None:
        from apps.sources.fasttext_langid import LangPrediction

        with patch(
            "apps.sources.fasttext_langid.predict",
            return_value=LangPrediction(language="de", confidence=0.95),
        ):
            self.assertFalse(language_filter.is_english("Hallo Welt"))


class FilterContentRecordsTests(TestCase):
    def setUp(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.runtime_flags import invalidate

        AppSetting.objects.update_or_create(
            key="fasttext_langid.candidate_filter.enabled",
            defaults={"value": "true", "description": ""},
        )
        invalidate("fasttext_langid.candidate_filter.enabled")

    def test_empty_records_returns_empty_dict(self) -> None:
        self.assertEqual(language_filter.filter_english_content_records({}), {})

    def test_unavailable_fasttext_returns_input_verbatim(self) -> None:
        records = {1: _FakeRecord("anything"), 2: _FakeRecord("else")}
        with patch(
            "apps.sources.fasttext_langid.is_available",
            return_value=False,
        ):
            kept = language_filter.filter_english_content_records(records)
            self.assertEqual(kept, records)

    def test_disabled_toggle_returns_input_verbatim(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.runtime_flags import invalidate

        AppSetting.objects.update_or_create(
            key="fasttext_langid.candidate_filter.enabled",
            defaults={"value": "false", "description": ""},
        )
        invalidate("fasttext_langid.candidate_filter.enabled")
        records = {1: _FakeRecord("This is English text")}
        kept = language_filter.filter_english_content_records(records)
        self.assertEqual(kept, records)

    def test_drops_non_english(self) -> None:
        from apps.sources.fasttext_langid import LangPrediction

        records = {
            1: _FakeRecord("Hello world this is plainly English"),
            2: _FakeRecord("Hallo Welt das ist offensichtlich Deutsch"),
        }

        def fake_predict(text: str):
            if "Welt" in text:
                return LangPrediction(language="de", confidence=0.97)
            return LangPrediction(language="en", confidence=0.99)

        with (
            patch(
                "apps.sources.fasttext_langid.is_available",
                return_value=True,
            ),
            patch(
                "apps.sources.fasttext_langid.predict",
                side_effect=fake_predict,
            ),
        ):
            kept = language_filter.filter_english_content_records(records)

        self.assertIn(1, kept)
        self.assertNotIn(2, kept)

    def test_empty_title_kept(self) -> None:
        records = {1: _FakeRecord("")}
        with patch(
            "apps.sources.fasttext_langid.is_available",
            return_value=True,
        ):
            kept = language_filter.filter_english_content_records(records)
        self.assertIn(1, kept)
