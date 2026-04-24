"""Embedding-provider Protocol + shared helpers (plan Part 1).

The Protocol mirrors the pattern in ``apps/sources/token_bucket.py`` —
minimal interface, no forced inheritance. Providers are plain classes that
happen to satisfy the Protocol via duck typing.

Design notes (performance-first):
  * ``EmbedResult`` holds a single pre-allocated ``np.ndarray`` of shape
    ``(n, dim)`` dtype ``float32``. No Python list-of-lists; no per-item
    allocations. The same array is passed by reference through ``_flush``.
  * ``embed()`` batch size is chosen by ``hardware_profile.recommended_batch_size``
    (plan Part 8a) — each provider implementation caps at its own API limit.
  * L2 normalisation happens once, inside the provider, if the API does not
    already normalise. The ``normalised`` flag tells the caller whether to
    skip the redundant L2-norm step in ``_flush_embeddings_slice``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class EmbedResult:
    """Output of ``EmbeddingProvider.embed()``.

    Attributes:
        vectors: ``np.ndarray`` of shape ``(n, dim)`` dtype ``float32``.
                 L2-normalised iff ``normalised=True``.
        tokens_input: Total input tokens consumed (for cost / rate-limit).
                      ``0`` for local providers.
        cost_usd: Incremental spend. ``0.0`` for local providers.
        provider_signature: Model-version string to store in
                            ``embedding_model_version``. Format:
                            ``"{provider}:{model}:{dim}"`` for remote providers,
                            ``"{model}:{dim}"`` for the local backward-compat path.
        normalised: True iff ``vectors`` are already unit-norm.
    """

    vectors: np.ndarray
    tokens_input: int = 0
    cost_usd: float = 0.0
    provider_signature: str = ""
    normalised: bool = True


class EmbeddingProvider(Protocol):
    """Contract for every embedding backend.

    ``name`` / ``signature`` / ``dimension`` / ``max_tokens`` are read at
    batch-dispatch time; implementations should treat them as stable for the
    lifetime of a single call (changing mid-call would cause dim mismatches).
    """

    name: str                # "local" | "openai" | "gemini"
    signature: str           # matches embedding_model_version
    dimension: int           # vector length
    max_tokens: int          # model context limit
    tokenizer_name: str      # e.g. "cl100k_base", "bge-m3"

    def embed(
        self,
        texts: Sequence[str],
        *,
        batch_size: int | None = None,
        job_id: str | None = None,
    ) -> EmbedResult: ...

    def embed_single(self, text: str) -> np.ndarray:
        """Embed one text, chunking long inputs with 10% overlap + mean-pool.

        Returns a single L2-normalised vector of length ``self.dimension``.
        Used by the quality gate (plan Part 9) for stability re-sampling and
        by the audit (plan Part 3) for resample comparisons.
        """
        ...

    def healthcheck(self) -> None:
        """Raise a ``ProviderError`` subclass if the provider is misconfigured."""
        ...

    def should_pause(self) -> str | None:
        """Return a pause reason string, or ``None`` if the job should continue.

        Checked at batch boundaries inside ``embed()`` so long API runs can be
        interrupted cleanly. Default implementation reads
        ``AppSetting("system.master_pause")`` and the current ``SyncJob`` status.
        """
        ...


# ---------------------------------------------------------------------------
# Shared helpers (no Protocol membership requirements)
# ---------------------------------------------------------------------------


def compute_signature(provider_name: str, model_name: str, dimension: int) -> str:
    """Return the canonical signature string stored in ``embedding_model_version``.

    Backward-compatible format for the local provider preserves existing
    signatures: ``"{model}:{dim}"`` (no provider prefix). API providers include
    the provider name so switching backends invalidates old signatures cleanly.
    """
    if provider_name == "local":
        return f"{model_name}:{dimension}"
    return f"{provider_name}:{model_name}:{dimension}"


def default_should_pause() -> str | None:
    """Read pause state from AppSetting; shared default implementation.

    Returns a reason string (e.g. ``"system_master_pause"``) or ``None``.
    Kept as a module function so each provider's ``should_pause`` can call it
    without Protocol inheritance.
    """
    try:
        from apps.core.models import AppSetting

        master = AppSetting.objects.filter(key="system.master_pause").first()
        if master and str(master.value).lower() in ("true", "1", "yes"):
            return "system_master_pause"
    except Exception:
        return None
    return None


def l2_normalise_inplace(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise rows of ``matrix`` in place. No-op if rows already unit.

    Returns the same array for chained use. Uses a single fused divide per row
    to minimise memory traffic (the hot path processes up to 128-row batches
    of 3072-dim float32 vectors per call = 1.5 MB each).
    """
    if matrix.size == 0:
        return matrix
    # Compute norms; avoid division by zero.
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    # Cheap early-out: if mean norm already very close to 1.0, skip.
    if np.isclose(norms.mean(), 1.0, rtol=0, atol=1e-4):
        return matrix
    np.divide(matrix, np.where(norms > 0, norms, 1.0), out=matrix)
    return matrix


def mean_pool_chunks(chunk_vectors: np.ndarray) -> np.ndarray:
    """Mean-pool chunked embeddings then L2-normalise.

    Standard technique from Reimers & Gurevych 2019 (SBERT) for combining
    chunked long-text embeddings into a single document vector.
    """
    if chunk_vectors.ndim != 2:
        raise ValueError("chunk_vectors must be 2-D (n_chunks, dim)")
    pooled = chunk_vectors.mean(axis=0).astype(np.float32, copy=False)
    norm = float(np.linalg.norm(pooled))
    if norm > 0:
        pooled = pooled / norm
    return pooled


__all__ = [
    "EmbedResult",
    "EmbeddingProvider",
    "compute_signature",
    "default_should_pause",
    "l2_normalise_inplace",
    "mean_pool_chunks",
]
