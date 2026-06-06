"""Co-located focused coverage tests for two ``passage_relevance`` helpers.

Targets:
    * ``_EmbeddingResources.__init__`` — the custom constructor that accepts
      either ``provider`` or the legacy ``model`` keyword and falls back to
      ``model`` when ``provider`` is None.
    * ``_load_embedding_resources`` — wires the active provider, signature and
      active OPQ codebook into one ``_EmbeddingResources`` bundle.

Both helpers are DB-free here (the model/embeddings calls are patched), so the
tests run under ``SimpleTestCase``. Kept next to ``passage_relevance.py``
(stem ``tests_passage_relevance``) so a per-file coverage run that resolves
``services/passage_relevance.py`` -> ``services/tests_passage_relevance.py``
still executes the constructor and loader bodies.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.pipeline.services import passage_relevance as pr


class EmbeddingResourcesInitTests(SimpleTestCase):
    def test_provider_keyword_is_stored_directly(self) -> None:
        # When `provider` is supplied it wins outright (the `if provider is
        # not None` branch of __init__).
        provider = MagicMock(name="provider")
        res = pr._EmbeddingResources(
            provider=provider,
            signature="sig-1",
            codebook=None,
            opq_version="",
        )

        self.assertIs(res.provider, provider)
        self.assertEqual(res.signature, "sig-1")
        self.assertIsNone(res.codebook)
        self.assertEqual(res.opq_version, "")

    def test_falls_back_to_model_when_provider_is_none(self) -> None:
        # Legacy call sites pass `model=`; with `provider` None the constructor
        # must fall back to the `model` value (the else side of __init__).
        legacy_model = MagicMock(name="legacy_model")
        codebook = SimpleNamespace(corpus_signature="opq-v9")
        res = pr._EmbeddingResources(
            model=legacy_model,
            signature="sig-2",
            codebook=codebook,
            opq_version="opq-v9",
        )

        self.assertIs(res.provider, legacy_model)
        self.assertIs(res.codebook, codebook)
        self.assertEqual(res.opq_version, "opq-v9")


class LoadEmbeddingResourcesTests(SimpleTestCase):
    def test_bundles_active_provider_signature_and_codebook(self) -> None:
        # Exercises the body of `_load_embedding_resources`: load provider,
        # read signature, fetch the active OPQ codebook, and derive opq_version
        # from the codebook's corpus_signature.
        cb = SimpleNamespace(corpus_signature="opq-2026-06")
        fake_filter = MagicMock()
        fake_filter.first.return_value = cb

        with (
            patch("apps.content.models.OPQCodebook") as codebook_model,
            patch(
                "apps.pipeline.services.embeddings._load_model",
                return_value="provider-handle",
            ),
            patch(
                "apps.pipeline.services.embeddings.get_current_embedding_signature",
                return_value="sig-load",
            ),
        ):
            codebook_model.objects.filter.return_value = fake_filter
            res = pr._load_embedding_resources()

        self.assertEqual(res.provider, "provider-handle")
        self.assertEqual(res.signature, "sig-load")
        self.assertIs(res.codebook, cb)
        self.assertEqual(res.opq_version, "opq-2026-06")

    def test_empty_opq_version_when_no_active_codebook(self) -> None:
        fake_filter = MagicMock()
        fake_filter.first.return_value = None

        with (
            patch("apps.content.models.OPQCodebook") as codebook_model,
            patch(
                "apps.pipeline.services.embeddings._load_model",
                return_value="provider-handle",
            ),
            patch(
                "apps.pipeline.services.embeddings.get_current_embedding_signature",
                return_value="sig-load",
            ),
        ):
            codebook_model.objects.filter.return_value = fake_filter
            res = pr._load_embedding_resources()

        self.assertIsNone(res.codebook)
        self.assertEqual(res.opq_version, "")
