"""
Stateless ML compute endpoints for Celery workers and external integrations.

These endpoints provide advanced NLP (spaCy) and sentence embedding
capabilities as a network-accessible service so callers do not need to
load the heavy models in their own process.

They do NOT touch the database or hold any runtime orchestration logic.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.api.query_params import coerce_int
from apps.api.throttles import MLEmbedThrottle as _MLEmbedThrottle
from apps.pipeline.services.distiller import distill_body
from apps.pipeline.services.embeddings import (
    _get_batch_size,
    _l2_normalize,
    _encode_batch_via_provider,
)


class MLDistillView(APIView):
    """
    POST /api/ml/distill/
    Accepts: { "sentences": ["...", "..."], "max_sentences": int (optional) }
    Returns: { "distilled": "..." }
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [_MLEmbedThrottle]

    def post(self, request):
        sentences = request.data.get("sentences", [])
        if not isinstance(sentences, list):
            return Response(
                {"error": "'sentences' must be a list of strings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Bug fix 2026-05-04: bare int(...) crashed with HTTP 500 on
        # `{"max_sentences": "foo"}`. Routed through coerce_int so a
        # typo falls back to the default 5 and is clamped to a sane
        # range — distill_body misbehaves badly with negative values.
        max_sentences = coerce_int(
            request.data.get("max_sentences"),
            default=5,
            min_value=1,
            max_value=100,
        )

        try:
            distilled_text = distill_body(sentences, max_sentences=max_sentences)
            return Response({"distilled": distilled_text})
        except Exception as e:  # noqa: BLE001 — distiller errors must not 500 the worker; surface message to caller.
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MLEmbedView(APIView):
    """
    POST /api/ml/embed/
    Accepts: { "texts": ["...", "..."] }
    Returns: { "embeddings": [[0.1, ...], ...] }
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [_MLEmbedThrottle]

    def post(self, request):
        texts = request.data.get("texts", [])
        if not isinstance(texts, list):
            return Response(
                {"error": "'texts' must be a list of strings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not texts:
            return Response({"embeddings": []})

        try:
            batch_size = _get_batch_size()
            raw_vectors = _encode_batch_via_provider(
                batch_texts=texts,
                model=None,
                batch_size=batch_size,
                job_id=None,
            )

            # Normalize for cosine similarity operations
            vectors = _l2_normalize(raw_vectors)

            return Response({"embeddings": vectors.tolist()})
        except Exception as e:  # noqa: BLE001  # API endpoint: surface ANY model/inference failure as a 500 with the exception message so the client can recover or report it.
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
