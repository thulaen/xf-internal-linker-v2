"""Local BGE provider (plan Part 1) — wraps the existing sentence-transformers path.

Delegates all model loading / caching / GPU handling to the helpers already
in ``embeddings.py`` (``_load_model``, ``_get_model_name``, ``_resolve_device``).
Zero duplication: this class is a thin adapter so the hot loop can talk to a
Protocol instead of directly touching the model.

Performance notes:
  * Model is loaded once per process via the existing ``_model_cache`` dict.
  * Batch vectors come back as ``np.ndarray`` float32 directly from
    ``SentenceTransformer.encode(convert_to_numpy=True)`` — no list round-trip.
  * L2 normalisation is done in-place by the caller (still, via the existing
    ``_l2_normalize`` C++ extension path) — we flag ``normalised=False`` so the
    caller keeps doing it. Legacy behaviour preserved exactly.
"""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np

from .base import (
    EmbedResult,
    compute_signature,
    default_should_pause,
    mean_pool_chunks,
)
from .errors import ProviderError

logger = logging.getLogger(__name__)


class LocalBGEProvider:
    """Local sentence-transformers provider (BAAI/bge-m3 by default).

    ``embed()`` forwards to the existing ``_load_model`` + ``model.encode`` path.
    Supports any sentence-transformers model (swap via AppSetting
    ``embedding.model``). Dimension is auto-detected, so high-dim models like
    BGE-M3-large (1024) and mxbai-large (1024) slot in without schema changes.
    """

    name = "local"
    tokenizer_name = "sentence-transformers"
    # BGE-M3 supports 8192 tokens; sentence-transformers typically truncates
    # to model.max_seq_length. Expose the upper bound here.
    max_tokens = 8192

    def __init__(self) -> None:
        # Lazy-resolve at embed time so hot-reloading AppSettings works.
        self._cached_model_name: str | None = None
        self._cached_dim: int | None = None
        self._cached_signature: str | None = None

    # --- Properties (lazy; computed from the loaded model) ---------------

    @property
    def model_name(self) -> str:
        if self._cached_model_name is None:
            from apps.pipeline.services.embeddings import _get_model_name
            self._cached_model_name = _get_model_name()
        return self._cached_model_name

    @property
    def dimension(self) -> int:
        if self._cached_dim is None:
            from apps.pipeline.services.embeddings import (
                get_current_embedding_dimension,
            )
            self._cached_dim = int(
                get_current_embedding_dimension(model_name=self.model_name)
            )
        return self._cached_dim

    @property
    def signature(self) -> str:
        if self._cached_signature is None:
            self._cached_signature = compute_signature(
                self.name, self.model_name, self.dimension
            )
        return self._cached_signature

    # --- Operations -------------------------------------------------------

    def embed(
        self,
        texts: Sequence[str],
        *,
        batch_size: int | None = None,
        job_id: str | None = None,
    ) -> EmbedResult:
        """Encode ``texts`` in one call; returns unnormalised float32 matrix.

        The caller (``_flush_embeddings_slice``) runs the C++ L2-norm over the
        result afterwards, so we flag ``normalised=False`` to avoid double work.
        """
        if not texts:
            return EmbedResult(
                vectors=np.empty((0, self.dimension), dtype=np.float32),
                provider_signature=self.signature,
                normalised=False,
            )

        from apps.pipeline.services.embeddings import (
            _get_configured_batch_size,
            _load_model,
        )

        effective_bs = batch_size or _get_configured_batch_size()
        try:
            model = _load_model(self.model_name)
        except Exception as exc:
            raise ProviderError(f"Failed to load local model: {exc}") from exc

        try:
            vectors = model.encode(
                list(texts),
                batch_size=effective_bs,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except Exception as exc:
            raise ProviderError(f"Local encode failed: {exc}") from exc

        # Ensure float32 contiguous for the downstream L2-norm path.
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32, copy=False)
        if not vectors.flags.c_contiguous:
            vectors = np.ascontiguousarray(vectors)

        return EmbedResult(
            vectors=vectors,
            tokens_input=0,
            cost_usd=0.0,
            provider_signature=self.signature,
            normalised=False,
        )

    def embed_single(self, text: str) -> np.ndarray:
        """Single-text embed with chunked mean-pool for long inputs.

        Uses the model's own tokenizer to count tokens; falls back to
        char-length / 4 if unavailable.
        """
        if not text:
            return np.zeros(self.dimension, dtype=np.float32)

        # Fast path: short text, one encode call.
        chunks = self._split_text_for_chunking(text)
        if len(chunks) == 1:
            result = self.embed([chunks[0]])
            vec = result.vectors[0]
            norm = float(np.linalg.norm(vec))
            return (vec / norm).astype(np.float32, copy=False) if norm > 0 else vec

        # Long-text path: chunk, encode all, mean-pool.
        result = self.embed(chunks)
        return mean_pool_chunks(result.vectors)

    def healthcheck(self) -> None:
        try:
            from apps.pipeline.services.embeddings import _load_model
            _load_model(self.model_name)
        except Exception as exc:
            raise ProviderError(f"Local model healthcheck failed: {exc}") from exc

    def should_pause(self) -> str | None:
        return default_should_pause()

    # --- Chunking --------------------------------------------------------

    def _split_text_for_chunking(self, text: str) -> list[str]:
        """Split ``text`` into chunks sized to ``max_tokens`` with 10% overlap.

        Uses the model's tokenizer when available (exact token counts);
        falls back to a character heuristic (~4 chars/token).
        """
        try:
            from apps.pipeline.services.embeddings import _load_model
            model = _load_model(self.model_name)
            tokenizer = getattr(model, "tokenizer", None)
            if tokenizer is None:
                raise AttributeError
            token_ids = tokenizer.encode(text, add_special_tokens=False)
        except Exception:
            # Fallback: char-based. 4 chars ~= 1 token (SBERT corpus rule-of-thumb).
            max_chars = self.max_tokens * 4
            if len(text) <= max_chars:
                return [text]
            overlap = max_chars // 10
            stride = max_chars - overlap
            chunks = [
                text[i : i + max_chars]
                for i in range(0, len(text), stride)
                if text[i : i + max_chars]
            ]
            return chunks or [text]

        if len(token_ids) <= self.max_tokens:
            return [text]

        overlap = self.max_tokens // 10
        stride = self.max_tokens - overlap
        chunk_texts: list[str] = []
        for i in range(0, len(token_ids), stride):
            piece = token_ids[i : i + self.max_tokens]
            if not piece:
                break
            try:
                chunk_texts.append(tokenizer.decode(piece, skip_special_tokens=True))
            except Exception:
                # Decode failure is non-fatal; skip the chunk.
                continue
        return chunk_texts or [text]
