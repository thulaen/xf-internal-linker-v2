"""DB-free tests for the stateless ML compute endpoints.

``MLDistillView`` and ``MLEmbedView`` are thin DRF views that validate
the request body, call a pipeline service, and shape the response. We
drive ``.post()`` directly with a fake request and mock every pipeline
call, so no model, GPU, network, or database is touched.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.api.ml_views import MLDistillView, MLEmbedView


def _fake_request(data: dict) -> SimpleNamespace:
    """Minimal stand-in for a DRF request — only ``.data`` is read."""
    return SimpleNamespace(data=data)


class MLDistillViewTests(SimpleTestCase):
    def test_when_sentences_not_a_list_then_400_with_message(self) -> None:
        resp = MLDistillView().post(_fake_request({"sentences": "nope"}))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            resp.data, {"error": "'sentences' must be a list of strings."}
        )

    def test_when_valid_then_returns_distilled_text(self) -> None:
        with patch(
            "apps.api.ml_views.distill_body", return_value="short"
        ) as mock_distill:
            resp = MLDistillView().post(
                _fake_request({"sentences": ["a", "b"], "max_sentences": 3})
            )
        self.assertEqual(resp.data, {"distilled": "short"})
        mock_distill.assert_called_once_with(["a", "b"], max_sentences=3)

    def test_when_max_sentences_garbage_then_falls_back_to_five(self) -> None:
        with patch(
            "apps.api.ml_views.distill_body", return_value="x"
        ) as mock_distill:
            MLDistillView().post(
                _fake_request({"sentences": ["a"], "max_sentences": "foo"})
            )
        self.assertEqual(mock_distill.call_args.kwargs["max_sentences"], 5)

    def test_when_distiller_raises_then_500_with_error_message(self) -> None:
        with patch(
            "apps.api.ml_views.distill_body", side_effect=ValueError("boom")
        ):
            resp = MLDistillView().post(_fake_request({"sentences": ["a"]}))
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.data, {"error": "boom"})


class MLEmbedViewTests(SimpleTestCase):
    def test_when_texts_not_a_list_then_400_with_message(self) -> None:
        resp = MLEmbedView().post(_fake_request({"texts": 42}))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {"error": "'texts' must be a list of strings."})

    def test_when_texts_empty_then_returns_empty_embeddings(self) -> None:
        resp = MLEmbedView().post(_fake_request({"texts": []}))
        self.assertEqual(resp.data, {"embeddings": []})

    def test_when_valid_then_returns_normalized_vectors(self) -> None:
        normalized = MagicMock()
        normalized.tolist.return_value = [[1.0, 0.0]]
        with (
            patch("apps.api.ml_views._get_batch_size", return_value=8),
            patch(
                "apps.api.ml_views._encode_batch_via_provider", return_value="raw"
            ) as mock_encode,
            patch(
                "apps.api.ml_views._l2_normalize", return_value=normalized
            ) as mock_norm,
        ):
            resp = MLEmbedView().post(_fake_request({"texts": ["hi"]}))
        self.assertEqual(resp.data, {"embeddings": [[1.0, 0.0]]})
        mock_encode.assert_called_once_with(
            batch_texts=["hi"], model=None, batch_size=8, job_id=None
        )
        mock_norm.assert_called_once_with("raw")

    def test_when_encoder_raises_then_500_with_error_message(self) -> None:
        with (
            patch("apps.api.ml_views._get_batch_size", return_value=8),
            patch(
                "apps.api.ml_views._encode_batch_via_provider",
                side_effect=RuntimeError("model down"),
            ),
        ):
            resp = MLEmbedView().post(_fake_request({"texts": ["hi"]}))
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.data, {"error": "model down"})
