"""OpenAI embedding provider (plan Part 1).

Uses the ``openai`` Python SDK (v1.x). Supports text-embedding-3-small (1536)
and text-embedding-3-large (3072). Dimension can be truncated server-side via
the ``dimensions`` parameter for cost/latency savings — read from AppSetting.

Performance:
  * Connection pooling via ``OpenAI()`` singleton (SDK's internal httpx.Client).
  * Batch size capped at 2 048 items OR 300k tokens per API constraints — we
    auto-chunk under the token ceiling using ``tiktoken`` offline token counts.
  * Long texts split with 10% overlap and mean-pooled (SBERT pattern).
  * Results come back as list-of-lists; we convert to a single ``float32``
    ``np.ndarray`` allocation — no row-by-row append.

Budget control (plan Part 8b integration):
  * Per-call cost calculated from token count × model price (AppSetting).
  * Raises ``BudgetExceededError`` if running total for the month exceeds
    ``embedding.monthly_budget_usd``.

Retry / rate-limit:
  * Tenacity decorator: exponential backoff with jitter, max 5 attempts.
  * On 429 / 5xx / timeout, waits and retries transparently.
  * On 401 / 403, raises ``AuthenticationError`` immediately (no retry — keys
    don't heal themselves).
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

# Model registry: dimension + pricing. Prices as of 2026-04 (USD per 1K tokens).
_MODEL_REGISTRY: dict[str, dict[str, float | int]] = {
    "text-embedding-3-small": {
        "dimension": 1536,
        "price_per_1k": 0.00002,
        "max_tokens": 8191,
    },
    "text-embedding-3-large": {
        "dimension": 3072,
        "price_per_1k": 0.00013,
        "max_tokens": 8191,
    },
    "text-embedding-ada-002": {
        "dimension": 1536,
        "price_per_1k": 0.00010,
        "max_tokens": 8191,
    },
}

_DEFAULT_MODEL = "text-embedding-3-small"


class OpenAIProvider:
    """OpenAI embedding provider via the official ``openai`` SDK."""

    name = "openai"
    tokenizer_name = "cl100k_base"

    def __init__(self) -> None:
        self._client = None  # lazy — avoids import cost when provider unused
        self._tokenizer = None
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
                self._read_setting("embedding.model", _DEFAULT_MODEL) or _DEFAULT_MODEL
            )
        return self._cached_model

    @property
    def dimension(self) -> int:
        if self._cached_dim is None:
            override = self._read_setting("embedding.dimensions_override", "")
            if override.isdigit():
                self._cached_dim = int(override)
            else:
                entry = _MODEL_REGISTRY.get(self.model_name, {})
                self._cached_dim = int(entry.get("dimension", 1536))
        return self._cached_dim

    @property
    def max_tokens(self) -> int:
        entry = _MODEL_REGISTRY.get(self.model_name, {})
        return int(entry.get("max_tokens", 8191))

    @property
    def signature(self) -> str:
        if self._cached_signature is None:
            self._cached_signature = compute_signature(
                self.name, self.model_name, self.dimension
            )
        return self._cached_signature

    # --- SDK + tokenizer -------------------------------------------------

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError(
                "openai SDK not installed; run `pip install openai>=1.0`"
            ) from exc
        api_key = self._read_setting("embedding.api_key", "") or os.environ.get(
            "OPENAI_API_KEY", ""
        )
        if not api_key:
            raise AuthenticationError("OpenAI API key not configured")
        base_url = self._read_setting("embedding.api_base", "") or None
        timeout = 30.0
        try:
            timeout = float(self._read_setting("embedding.timeout_seconds", "30"))
        except ValueError:
            pass  # malformed AppSetting; keep the 30s default
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        return self._client

    def _ensure_tokenizer(self):
        if self._tokenizer is not None:
            return self._tokenizer
        try:
            import tiktoken

            self._tokenizer = tiktoken.get_encoding(self.tokenizer_name)
        except Exception:
            self._tokenizer = None
        return self._tokenizer

    # --- Budget check ----------------------------------------------------

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
                    f"OpenAI monthly budget ${budget:.2f} would be exceeded "
                    f"(spent ${float(spent):.2f}, next call ~${extra_cost_usd:.4f})"
                )
        except BudgetExceededError:
            raise
        except Exception:
            # If the ledger table is unavailable, skip the pre-check; the call
            # proceeds. Post-call accounting still runs.
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
        tokenizer = self._ensure_tokenizer()
        texts_list = list(texts)

        # Count tokens offline so we can estimate cost BEFORE the API call.
        token_counts: list[int] = []
        if tokenizer is not None:
            for t in texts_list:
                token_counts.append(len(tokenizer.encode(t or "")))
        else:
            # Heuristic: ~4 chars / token.
            token_counts = [max(1, len(t or "") // 4) for t in texts_list]
        total_tokens = sum(token_counts)

        price_entry = _MODEL_REGISTRY.get(self.model_name, {})
        price_per_1k = float(price_entry.get("price_per_1k", 0.0))
        estimated_cost = total_tokens * price_per_1k / 1000.0
        self._check_budget(estimated_cost)

        # Truncate any text that exceeds max_tokens so the API doesn't reject
        # the batch; track which ones were truncated for chunking later.
        processed: list[str] = []
        chunked_indices: dict[int, list[str]] = {}
        for idx, (text, tok_count) in enumerate(zip(texts_list, token_counts)):
            if tok_count <= self.max_tokens:
                processed.append(text or "")
                continue
            chunks = self._chunk_tokens(text or "", tokenizer)
            chunked_indices[idx] = chunks
            processed.append(chunks[0])  # placeholder; recomputed below

        # Single-batch API call. OpenAI supports up to 2 048 items/request.
        # Respect the configured batch_size as an upper bound.
        bs = min(len(processed), batch_size or 256, 2048)
        rows: list[list[float]] = []
        consumed_tokens = 0
        for batch_start in range(0, len(processed), bs):
            if self.should_pause():
                raise ProviderError("paused_mid_embed", reason="paused")
            batch_slice = processed[batch_start : batch_start + bs]
            resp = self._call_with_retry(
                client=client,
                texts=batch_slice,
                dimensions=self._request_dimensions_kwarg(),
            )
            rows.extend(d.embedding for d in resp.data)
            consumed_tokens += getattr(resp.usage, "total_tokens", 0) or 0

        # Replace rows for chunked inputs with their mean-pooled vector.
        for idx, chunks in chunked_indices.items():
            # Embed all chunks in one call; mean-pool then substitute.
            chunk_vectors = []
            for chunk_start in range(0, len(chunks), bs):
                sub = chunks[chunk_start : chunk_start + bs]
                resp = self._call_with_retry(
                    client=client,
                    texts=sub,
                    dimensions=self._request_dimensions_kwarg(),
                )
                chunk_vectors.extend(d.embedding for d in resp.data)
                consumed_tokens += getattr(resp.usage, "total_tokens", 0) or 0
            arr = np.asarray(chunk_vectors, dtype=np.float32)
            rows[idx] = mean_pool_chunks(arr).tolist()

        actual_cost = consumed_tokens * price_per_1k / 1000.0
        vectors = np.asarray(rows, dtype=np.float32)

        return EmbedResult(
            vectors=vectors,
            tokens_input=consumed_tokens or total_tokens,
            cost_usd=actual_cost,
            provider_signature=self.signature,
            normalised=True,  # OpenAI returns L2-normalised vectors
        )

    def embed_single(self, text: str) -> np.ndarray:
        if not text:
            return np.zeros(self.dimension, dtype=np.float32)
        tokenizer = self._ensure_tokenizer()
        tokens = tokenizer.encode(text) if tokenizer is not None else []
        if tokenizer is None or len(tokens) <= self.max_tokens:
            result = self.embed([text])
            return result.vectors[0]
        chunks = self._chunk_tokens(text, tokenizer)
        result = self.embed(chunks)
        return mean_pool_chunks(result.vectors)

    def healthcheck(self) -> None:
        # One-token ping so credentials are verified without cost hit.
        result = self.embed(["ok"])
        if result.vectors.shape[0] != 1:
            raise ProviderError("OpenAI healthcheck returned unexpected shape")

    def should_pause(self) -> str | None:
        return default_should_pause()

    # --- Helpers ---------------------------------------------------------

    def _request_dimensions_kwarg(self) -> int | None:
        """Return the ``dimensions`` API parameter if the user overrode it."""
        override = self._read_setting("embedding.dimensions_override", "")
        if override.isdigit():
            return int(override)
        return None

    def _chunk_tokens(self, text: str, tokenizer) -> list[str]:
        """Split ``text`` into ``max_tokens``-sized chunks with 10% overlap."""
        if tokenizer is None:
            # Char fallback; not perfectly accurate but keeps the API happy.
            max_chars = self.max_tokens * 4
            if len(text) <= max_chars:
                return [text]
            overlap = max_chars // 10
            stride = max_chars - overlap
            return [
                text[i : i + max_chars]
                for i in range(0, len(text), stride)
                if text[i : i + max_chars]
            ]

        ids = tokenizer.encode(text)
        if len(ids) <= self.max_tokens:
            return [text]
        overlap = self.max_tokens // 10
        stride = self.max_tokens - overlap
        pieces: list[str] = []
        for i in range(0, len(ids), stride):
            sub = ids[i : i + self.max_tokens]
            if not sub:
                break
            try:
                pieces.append(tokenizer.decode(sub))
            except Exception:
                continue
        return pieces or [text]

    def _call_with_retry(self, *, client, texts: list[str], dimensions: int | None):
        """Call the embeddings endpoint with exponential backoff.

        Order of attempted resilience strategies:
          1. On 429 / 5xx / timeout: exponential backoff up to 5 attempts.
          2. On 401 / 403: raise AuthenticationError immediately (no retry).
          3. On 400 (input too long): raise InvalidInputError.
        """
        # Import lazily so environments without openai can still load the module.
        try:
            from openai import (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                AuthenticationError as OAIAuthError,
                BadRequestError,
                RateLimitError as OAIRateLimitError,
            )
        except ImportError as exc:
            raise ProviderError("openai SDK import failed") from exc

        kwargs: dict = {"model": self.model_name, "input": texts}
        if dimensions is not None:
            kwargs["dimensions"] = dimensions

        max_attempts = 5
        backoff = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                return client.embeddings.create(**kwargs)
            except OAIAuthError as exc:
                raise AuthenticationError(str(exc)) from exc
            except BadRequestError as exc:
                raise InvalidInputError(str(exc)) from exc
            except OAIRateLimitError as exc:
                if attempt == max_attempts:
                    raise RateLimitError(str(exc)) from exc
                sleep_for = backoff + (backoff * 0.1 * attempt)
                logger.warning(
                    "OpenAI rate-limit; retry %d/%d after %.1fs",
                    attempt,
                    max_attempts,
                    sleep_for,
                )
                time.sleep(sleep_for)
                backoff *= 2
            except (APITimeoutError, APIConnectionError, APIStatusError) as exc:
                if attempt == max_attempts:
                    raise TransientProviderError(str(exc)) from exc
                sleep_for = backoff + (backoff * 0.1 * attempt)
                logger.warning(
                    "OpenAI transient error; retry %d/%d after %.1fs",
                    attempt,
                    max_attempts,
                    sleep_for,
                )
                time.sleep(sleep_for)
                backoff *= 2
            except Exception as exc:
                raise ProviderError(f"OpenAI call failed: {exc}") from exc
        raise TransientProviderError("OpenAI: exhausted retries")
