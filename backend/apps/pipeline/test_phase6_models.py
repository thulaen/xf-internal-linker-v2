"""Phase 6.3 — LDA (#18) + KenLM (#23) wrapper tests."""

from __future__ import annotations

import math
import unittest

from django.test import TestCase

from apps.pipeline.services import kenlm_fluency, lda_topics


class LdaTopicsTests(TestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(lda_topics.is_available(), bool)

    def test_empty_tokens_returns_empty(self) -> None:
        result = lda_topics.infer_topics([])
        self.assertIs(result, lda_topics.EMPTY_DISTRIBUTION)
        self.assertTrue(result.is_empty)

    def test_no_paths_configured_returns_empty(self) -> None:
        """No AppSetting paths → cold start → empty."""
        result = lda_topics.infer_topics(["hello", "world"])
        self.assertTrue(result.is_empty)

    def test_load_model_with_no_paths_returns_none(self) -> None:
        self.assertIsNone(lda_topics.load_model())

    def test_load_model_with_invalid_paths_returns_none(self) -> None:
        from apps.core.models import AppSetting

        for key, value in (
            (lda_topics.KEY_MODEL_PATH, "/tmp/nope/lda.model"),
            (lda_topics.KEY_DICT_PATH, "/tmp/nope/lda.dict"),
        ):
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": value, "description": ""}
            )
        self.assertIsNone(lda_topics.load_model())

    def test_fit_and_save_below_min_documents_returns_false(self) -> None:
        """< 2 documents → skip training cleanly."""
        ok = lda_topics.fit_and_save(
            documents=[["only", "one", "doc"]],
            model_path="/tmp/x.model",
            dict_path="/tmp/x.dict",
        )
        self.assertFalse(ok)

    @unittest.skipUnless(lda_topics.HAS_GENSIM, "gensim not installed")
    def test_fit_and_save_round_trip(self) -> None:
        """Train → save → load → infer round-trip."""
        import os
        import tempfile

        from apps.core.models import AppSetting

        documents = [
            ["python", "tutorial", "beginner"],
            ["python", "advanced", "patterns"],
            ["ruby", "rails", "tutorial"],
            ["machine", "learning", "tutorial"],
            ["python", "machine", "learning"],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            model_path = os.path.join(tmp, "lda.model")
            dict_path = os.path.join(tmp, "lda.dict")
            ok = lda_topics.fit_and_save(
                documents,
                model_path=model_path,
                dict_path=dict_path,
                num_topics=3,
                passes=2,
            )
            self.assertTrue(ok)
            for key, value in (
                (lda_topics.KEY_MODEL_PATH, model_path),
                (lda_topics.KEY_DICT_PATH, dict_path),
            ):
                AppSetting.objects.update_or_create(
                    key=key, defaults={"value": value, "description": ""}
                )
            result = lda_topics.infer_topics(["python", "tutorial"])
            self.assertFalse(result.is_empty)
            # Top topic probability should be > 0.
            self.assertGreater(result.weights[0][1], 0.0)


class KenlmFluencyTests(TestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(kenlm_fluency.is_available(), bool)

    def test_empty_sentence_returns_neutral(self) -> None:
        result = kenlm_fluency.score_fluency("")
        self.assertEqual(result.log_prob, kenlm_fluency.NEUTRAL_SCORE)
        self.assertEqual(result.token_count, 0)

    def test_no_model_path_returns_neutral(self) -> None:
        result = kenlm_fluency.score_fluency("Hello world.")
        self.assertEqual(result.log_prob, kenlm_fluency.NEUTRAL_SCORE)

    def test_invalid_model_path_returns_neutral(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=kenlm_fluency.KEY_MODEL_PATH,
            defaults={"value": "/tmp/no/such/file.arpa", "description": ""},
        )
        result = kenlm_fluency.score_fluency("Hello world.")
        self.assertEqual(result.log_prob, kenlm_fluency.NEUTRAL_SCORE)

    def test_load_model_with_no_path_returns_none(self) -> None:
        self.assertIsNone(kenlm_fluency.load_model())

    def test_perplexity_returns_inf_when_no_model(self) -> None:
        self.assertTrue(math.isinf(kenlm_fluency.perplexity("anything")))
