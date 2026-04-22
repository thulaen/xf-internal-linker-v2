"""Product-Quantisation wrapper for embedding compression (via FAISS).

Reference: Jégou, Hervé & Douze, Matthijs & Schmid, Cordelia (2011).
"Product quantization for nearest neighbor search." *IEEE Transactions
on Pattern Analysis and Machine Intelligence* 33(1): 117-128. INRIA
filed related patents (US8583657, US9043316) — this implementation
uses the open-source FAISS library, which Facebook AI Research
released under the MIT licence.

Why it matters: the project's embeddings are 1024-dim float32
vectors (BGE-M3), 4 kB each. At 100k pages that's 400 MB of
embeddings sitting in pgvector. PQ compresses each vector to
``m`` bytes (default 8) by splitting it into ``m`` sub-vectors and
replacing each sub-vector with the index of its nearest centroid in
a ``Ks=256``-entry codebook. That's ~97 % space savings with a 1-3 %
recall loss — Jégou et al. Table 2.

Wrapper choices:

- **FAISS is already pinned** (``faiss-gpu-cu12>=1.8.0``). No new
  dep — the duplication audit confirmed this.
- **Lazy import of faiss.** ``import faiss`` at module load would
  force every Django worker to pay the cost of FAISS's native
  library loader even if the worker never uses PQ. We import only
  inside ``fit`` / ``encode`` / ``decode`` so the rest of
  ``apps.sources`` stays import-cheap.
- **Explicit train/encode/decode separation.** A single ``IndexPQ``
  does all three, but keeping them as distinct methods lets tests
  verify the compression ratio and reconstruction error without
  wiring up a full nearest-neighbour search.
- **No persistence logic here.** Callers pickle
  ``quantizer.trained_state()`` and save it wherever is convenient
  (redis, S3, or on disk in a known path). This module only builds
  and applies the codebook.

Sizing defaults follow Jégou 2011 §IV: m=8 subvectors, Ks=256
centroids per codebook (8 bits per subvector → 8 bytes total per
vector). At dim=1024 each subvector is 1024/8 = 128-dim which the
paper reports works well in that range.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


#: Default number of subvectors per encoded vector. m=8 + Ks=256 →
#: 1 byte per subvector = 8 bytes total per vector (1024-dim source).
DEFAULT_SUBVECTORS_M: int = 8

#: Default number of centroids per subvector codebook (paper default).
DEFAULT_CENTROIDS_KS: int = 256

#: Minimum training-set size multiplier of Ks that FAISS will accept
#: without complaining. Jégou 2011 recommends at least 39 * Ks for
#: stable codebooks; we stick with FAISS's internal warning threshold.
_MIN_TRAIN_MULTIPLE: int = 39


@dataclass
class ProductQuantizer:
    """Thin wrapper over ``faiss.IndexPQ``.

    Lifecycle:

        1. Construct with dim + m + Ks.
        2. Call ``fit(training_vectors)`` once to learn the codebooks.
        3. Call ``encode(vectors)`` / ``decode(codes)`` repeatedly.

    ``fit`` must be called before ``encode``/``decode`` — attempting
    to use an untrained quantizer raises :class:`RuntimeError`.

    The wrapper is not thread-safe across ``fit`` calls, but
    ``encode`` and ``decode`` are safe once training is complete.
    """

    dimension: int
    m: int = DEFAULT_SUBVECTORS_M
    ks: int = DEFAULT_CENTROIDS_KS
    _index: Any = field(default=None, init=False, repr=False)
    _trained: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.dimension <= 0:
            raise ValueError("dimension must be > 0")
        if self.m <= 0:
            raise ValueError("m (subvectors) must be > 0")
        if self.dimension % self.m != 0:
            raise ValueError(
                f"dimension={self.dimension} must be divisible by m={self.m} "
                f"(subvectors have equal width)"
            )
        if self.ks <= 0:
            raise ValueError("ks (centroids) must be > 0")
        # FAISS stores codebook indices in n_bits per subvector, which
        # must be in [2, 16]. Derive from ks.
        n_bits = (self.ks - 1).bit_length()
        if not 2 <= n_bits <= 16:
            raise ValueError(
                f"ks={self.ks} → {n_bits} bits — FAISS requires 2..16. "
                f"Common choices: 256 (8), 1024 (10), 4096 (12)."
            )
        self._n_bits = n_bits

    # ── Public API ───────────────────────────────────────────────

    @property
    def bytes_per_vector(self) -> int:
        """Compressed size of a single encoded vector."""
        # FAISS packs m subvectors into ceil(m * n_bits / 8) bytes.
        bits = self.m * self._n_bits
        return (bits + 7) // 8

    @property
    def compression_ratio(self) -> float:
        """Source bytes per encoded byte (float32 source assumed)."""
        return (self.dimension * 4) / max(1, self.bytes_per_vector)

    @property
    def trained(self) -> bool:
        return self._trained

    def fit(self, training_vectors) -> None:
        """Learn the codebooks from *training_vectors* (shape [n, dim])."""
        import faiss  # lazy import
        import numpy as np

        arr = np.asarray(training_vectors, dtype=np.float32)
        if arr.ndim != 2:
            raise ValueError(
                f"training_vectors must be 2-D; got shape {arr.shape}"
            )
        if arr.shape[1] != self.dimension:
            raise ValueError(
                f"training_vectors have dim {arr.shape[1]}, "
                f"quantizer expects {self.dimension}"
            )
        min_rows = _MIN_TRAIN_MULTIPLE * self.ks
        if arr.shape[0] < min_rows:
            # FAISS will emit a warning on its own; surface it so the
            # caller sees it in their Celery logs.
            import logging

            logging.getLogger(__name__).warning(
                "ProductQuantizer.fit: training set has %d rows; "
                "Jégou 2011 recommends ≥ %d for stable codebooks.",
                arr.shape[0],
                min_rows,
            )
        self._index = faiss.IndexPQ(self.dimension, self.m, self._n_bits)
        self._index.train(arr)
        self._trained = True

    def encode(self, vectors):
        """Encode *vectors* to PQ codes. Returns uint8 array of shape [n, bytes_per_vector]."""
        self._require_trained()
        import numpy as np

        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[1] != self.dimension:
            raise ValueError(
                f"vectors must be 2-D with dim {self.dimension}; got {arr.shape}"
            )
        return self._index.sa_encode(arr)

    def decode(self, codes):
        """Reconstruct approximate float32 vectors from PQ codes."""
        self._require_trained()
        import numpy as np

        arr = np.asarray(codes, dtype=np.uint8)
        if arr.ndim != 2 or arr.shape[1] != self.bytes_per_vector:
            raise ValueError(
                f"codes must be 2-D with {self.bytes_per_vector} bytes/row; "
                f"got {arr.shape}"
            )
        return self._index.sa_decode(arr)

    def trained_state(self):
        """Return a ``bytes`` blob that can be persisted + reloaded via ``load_state``."""
        self._require_trained()
        import faiss  # lazy import

        return faiss.serialize_index(self._index)

    def load_state(self, blob) -> None:
        """Restore a previously-serialised quantizer. Skips fit() entirely."""
        import faiss  # lazy import

        self._index = faiss.deserialize_index(blob)
        self._trained = True

    # ── Internals ─────────────────────────────────────────────────

    def _require_trained(self) -> None:
        if not self._trained or self._index is None:
            raise RuntimeError(
                "ProductQuantizer: call fit(training_vectors) before "
                "encode/decode."
            )
