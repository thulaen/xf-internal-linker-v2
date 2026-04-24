"""Gemini embedding provider (plan Part 1).

Uses the ``google-genai`` Python SDK. Supports ``text-embedding-004`` (768 dim,
2 048-token context) and newer ``gemini-embedding-exp-03-07`` (3 072 dim).

Performance mirrors the OpenAI provider:
  * Connection pooling via ``google.genai.Client()`` singleton.
  * Batch size capped at 100 items per Gemini API constraint.
  * Long texts chunked with 10% overlap + SBERT-style mean pool.
  * Results normalised by the API; ``normalised=True`` so the caller skips L2.

Rate-limit + auth + budget handling parallel the OpenAI implementation so the
graceful-fallback logic in plan Part 8b can treat both identically.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Sequence

import numpy as np

from .base import (
    EmbedResult,
    compute_signature,
    default_should_pause,
    mean_pool_chunks,
)
from .errors import (
    AuthenticationError,
    BudgetExceededError,
    InvalidInputError,
    ProviderError,
    RateLimitError,
    TransientProviderError,
)

logger = logging.getLogger(__name__)

_MODEL_REGISTRY: dict[str, dict[str, float | int]] = {
    "text-embedding-004": {"dimension": 768, "price_per_1k": 0.000025, "max_tokens": 2048},
    "gemini-embedding-exp-03-07": {"dimension": 3072, "price_per_1k": 0.00013, "max_tokens": 2048},
}

_DEFAULT_MODEL = "text-embedding-004"
_BATCH_CEILING = 100  # Gemini SDK limit as of 2026-04


class GeminiProvider:
    """Gemini embedding provider via ``google-genai`` SDK."""

    name = "gemini"
    tokenizer_name = "gemini"

    def __init__(self) -> None:
        self._client = None
        self._cached_model: str | None = None
        self._cached_dim: int | None = None
        self._cached_signature: str | None = None

    # --- Config ----------------------------------------------------------

    def _read_setting(self, key: str, default: str = "") -> str:
        try:
            from apps.core.models import AppSetting
            row = AppSetting.objects.filter(key=key).first()
            return str(row.value) if row and row.value is not None else default
        except Exception:
            return default

    @property
    def model_name(self) -> str:
        if self._cached_model is None:
            self._cached_model = (
                self._read_setting("embedding.model", _DEFAULT_MODEL)
                or _DEFAULT_MODEL
            )
        return self._cached_model

    @property
    def dimension(self) -> int:
        if self._cached_dim is None:
            entry = _MODEL_REGISTRY.get(self.model_name, {})
            self._cached_dim = int(entry.get("dimension", 768))
        return self._cached_dim

    @property
    def max_tokens(self) -> int:
        entry = _MODEL_REGISTRY.get(self.model_name, {})
        return int(entry.get("max_tokens", 2048))

    @property
    def signature(self) -> str:
        if self._cached_signature is None:
            self._cached_signature = compute_signature(
                self.name, self.model_name, self.dimension
            )
        return self._cached_signature

    # --- SDK -------------------------------------------------------------

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from google import genai  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderError(
                "google-genai SDK not installed; run `pip install google-genai`"
            ) from exc
        api_key = self._read_setting("embedding.api_key", "") or os.environ.get(
            "GOOGLE_API_KEY", os.environ.get("GEMINI_API_KEY", "")
        )
        if not api_key:
            raise AuthenticationError("Gemini API key not configured")
        try:
            self._client = genai.Client(api_key=api_key)
        except Exception as exc:
            raise AuthenticationError(f"Gemini client init failed: {exc}") from exc
        return self._client

    # --- Budget ----------------------------------------------------------

    def _check_budget(self, extra_cost_usd: float) -> None:
        try:
            budget_str = self._read_setting("embedding.monthly_budget_usd", "50.0")
            budget = float(budget_str) if budget_str else 50.0
        except ValueError:
            budget = 50.0
        if budget <= 0:
            return
        try:
            from apps.pipeline.models import EmbeddingCostLedger
            from django.db.models import Sum
            from django.utils import timezone

            first_of_month = timezone.now().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            spent = (
                EmbeddingCostLedger.objects.filter(
                    provider=self.name, created_at__gte=first_of_month
                ).aggregate(total=Sum("cost_usd"))["total"]
                or 0.0
            )
            if float(spent) + extra_cost_usd > budget:
                raise BudgetExceededError(
                    f"Gemini monthly budget ${budget:.2f} would be exceeded "
                    f"(spent ${float(spent):.2f}, next call ~${extra_cost_usd:.4f})"
                )
        except BudgetExceededError:
            raise
        except Exception:
            return

    # --- Embed -----------------------------------------------------------

    def embed(
        self,
        texts: Sequence[str],
        *,
        batch_size: int | None = None,
        job_id: str | None = None,
    ) -> EmbedResult:
        if not texts:
            return EmbedResult(
                vectors=np.empty((0, self.dimension), dtype=np.float32),
                provider_signature=self.signature,
                normalised=True,
            )
        client = self._ensure_client()
        texts_list = list(texts)

        # Estimate tokens for budget gate (Gemini does not expose tiktoken-like
        # offline counters; use char heuristic which is acceptable for budget
        # pre-check — the post-call accounting uses the actual response tokens).
        est_tokens = sum(max(1, len(t or "") // 4) for t in texts_list)
        price_per_1k = float(_MODEL_REGISTRY.get(self.model_name, {}).get("price_per_1k", 0.0))
        estimated_cost = est_tokens * price_per_1k / 1000.0
        self._check_budget(estimated_cost)

        bs = min(batch_size or _BATCH_CEILING, _BATCH_CEILING)
        rows: list[list[float]] = [[] for _ in texts_list]
        consumed_tokens = 0

        for batch_start in range(0, len(texts_list), bs):
            if self.should_pause():
                raise ProviderError("paused_mid_embed", reason="paused")
            batch_slice = texts_list[batch_start : batch_start + bs]
            processed_slice: list[str] = []
            chunked_lookup: dict[int, list[str]] = {}
            for local_idx, t in enumerate(batch_slice):
                absolute_idx = batch_start + local_idx
                if self._est_tokens(t) <= self.max_tokens:
                    processed_slice.append(t or "")
                    continue
                chunks = self._chunk_chars(t or "")
                chunked_lookup[absolute_idx] = chunks
                processed_slice.append(chunks[0])

            try:
                response = self._call_with_retry(client, processed_slice)
            except ProviderError:
                raise

            # google-genai response: response.embeddings is a list; each has .values
            embeddings = self._extract_embeddings(response)
            for local_idx, vec in enumerate(embeddings):
                absolute_idx = batch_start + local_idx
                if absolute_idx not in chunked_lookup:
                    rows[absolute_idx] = list(vec)

            consumed_tokens += self._extract_token_count(response) or 0

            # Handle chunked items: embed their chunks, mean-pool.
            for absolute_idx, chunks in chunked_lookup.items():
                chunk_resp = self._call_with_retry(client, chunks)
                chunk_embs = self._extract_embeddings(chunk_resp)
                arr = np.asarray(chunk_embs, dtype=np.float32)
                rows[absolute_idx] = mean_pool_chunks(arr).tolist()
                consumed_tokens += self._extract_token_count(chunk_resp) or 0

        vectors = np.asarray(rows, dtype=np.float32)
        actual_cost = consumed_tokens * price_per_1k / 1000.0 if consumed_tokens else estimated_cost

        return EmbedResult(
            vectors=vectors,
            tokens_input=consumed_tokens or est_tokens,
            cost_usd=actual_cost,
            provider_signature=self.signature,
            normalised=True,
        )

    def embed_single(self, text: str) -> np.ndarray:
        if not text:
            return np.zeros(self.dimension, dtype=np.float32)
        if self._est_tokens(text) <= self.max_tokens:
            return self.embed([text]).vectors[0]
        chunks = self._chunk_chars(text)
        result = self.embed(chunks)
        return mean_pool_chunks(result.vectors)

    def healthcheck(self) -> None:
        result = self.embed(["ok"])
        if result.vectors.shape[0] != 1:
            raise ProviderError("Gemini healthcheck returned unexpected shape")

    def should_pause(self) -> str | None:
        return default_should_pause()

    # --- Helpers ---------------------------------------------------------

    def _est_tokens(self, text: str) -> int:
        return max(1, len(text or "") // 4)

    def _chunk_chars(self, text: str) -> list[str]:
        max_chars = self.max_tokens * 4
        if len(text) <= max_chars:
            return [text]
        overlap = max_chars // 10
        stride = max_chars - overlap
        return [text[i : i + max_chars] for i in range(0, len(text), stride) if text[i : i + max_chars]]

    def _extract_embeddings(self, response) -> list[list[float]]:
        # Handle two common google-genai shapes:
        #   response.embeddings -> List[ContentEmbedding(values=[...])]
        #   response['embedding']['values']  (older API)
        embeddings = getattr(response, "embeddings", None)
        if embeddings is not None:
            return [list(getattr(e, "values", [])) for e in embeddings]
        embedding = getattr(response, "embedding", None)
        if embedding is not None:
            return [list(getattr(embedding, "values", []))]
        if isinstance(response, dict):
            emb = response.get("embeddings") or response.get("embedding")
            if isinstance(emb, list):
                return [list(e.get("values", [])) for e in emb if isinstance(e, dict)]
            if isinstance(emb, dict):
                return [list(emb.get("values", []))]
        raise ProviderError("Unexpected Gemini response shape")

    def _extract_token_count(self, response) -> int | None:
        usage = getattr(response, "usage_metadata", None) or getattr(response, "metadata", None)
        if usage is None:
            return None
        return getattr(usage, "total_token_count", None) or getattr(usage, "total_tokens", None)

    def _call_with_retry(self, client, texts: list[str]):
        max_attempts = 5
        backoff = 1.0
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return client.models.embed_content(
                    model=self.model_name,
                    contents=texts,
                )
            except Exception as exc:
                msg = str(exc).lower()
                last_error = exc
                # Classify by message — google-genai exceptions are generic.
                if "401" in msg or "unauthor" in msg or "api key" in msg or "forbid" in msg:
                    raise AuthenticationError(str(exc)) from exc
                if "429" in msg or "rate" in msg or "quota" in msg:
                    if attempt == max_attempts:
                        raise RateLimitError(str(exc)) from exc
                    sleep_for = backoff + (backoff * 0.1 * attempt)
                    logger.warning(
                        "Gemini rate-limit; retry %d/%d after %.1fs",
                        attempt,
                        max_attempts,
                        sleep_for,
                    )
                    time.sleep(sleep_for)
                    backoff *= 2
                    continue
                if "400" in msg or "invalid" in msg:
                    raise InvalidInputError(str(exc)) from exc
                if attempt == max_attempts:
                    raise TransientProviderError(str(exc)) from exc
                sleep_for = backoff + (backoff * 0.1 * attempt)
                logger.warning(
                    "Gemini transient error; retry %d/%d after %.1fs",
                    attempt,
                    max_attempts,
                    sleep_for,
                )
                time.sleep(sleep_for)
                backoff *= 2
        raise TransientProviderError(f"Gemini: exhausted retries ({last_error})")
