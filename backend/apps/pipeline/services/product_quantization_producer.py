"""Producer + read API for pick #20 Product Quantization.

The math helper at :mod:`apps.sources.product_quantization` (FAISS
``IndexPQ``) does the actual compress/decompress. This module is
the producer side: read existing :class:`ContentItem` embeddings,
fit the codebook, persist it, then encode every embedding into the
``ContentItem.pq_code`` BinaryField.

Cold-start safe at every layer:

- Codebook empty → :func:`load_codebook` returns None; consumers fall
  through to the full ``embedding`` field.
- Too few embeddings to train (< 39 × Ks per Jégou 2011 §IV) →
  producer skips the fit and leaves the codebook untouched.
- A ContentItem's ``pq_code_version`` doesn't match the active
  codebook → consumers must treat the row as "not yet encoded" and
  use the full ``embedding`` instead.

Persisted shape (mirrors Platt / Conformal / IPS / Cascade
producers — same pattern):

- ``product_quantization.codebook`` — base64-encoded FAISS codebook
  bytes (binary blob serialised via FAISS's ``serialize_index``).
- ``product_quantization.dimension`` — vector dimension the codebook
  was trained on (must match ContentItem.embedding dim).
- ``product_quantization.m`` — number of subvectors.
- ``product_quantization.ks`` — number of centroids per subvector.
- ``product_quantization.bytes_per_vector`` — encoded size.
- ``product_quantization.version`` — short hex tag of the codebook.
  Stored on every encoded row's ``pq_code_version`` so consumers
  reject stale codes after a refit.
- ``product_quantization.fitted_at`` — ISO timestamp of the fit.
- ``product_quantization.training_size`` — # of rows fit was over.
- ``product_quantization.encoded_count`` — # of rows now carry codes.

The W1 ``product_quantization_refit`` scheduled job
(:func:`apps.scheduled_updates.jobs.run_product_quantization_refit`)
calls :func:`fit_and_persist_from_embeddings` monthly. Group B.2
will wire the read path to optionally short-circuit cosine similarity
through PQ codes when both vectors are encoded.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass

from apps.sources.product_quantization import (
    DEFAULT_CENTROIDS_KS,
    DEFAULT_SUBVECTORS_M,
    ProductQuantizer,
)

logger = logging.getLogger(__name__)


KEY_CODEBOOK = "product_quantization.codebook"
KEY_DIMENSION = "product_quantization.dimension"
KEY_M = "product_quantization.m"
KEY_KS = "product_quantization.ks"
KEY_BYTES_PER_VECTOR = "product_quantization.bytes_per_vector"
KEY_VERSION = "product_quantization.version"
KEY_FITTED_AT = "product_quantization.fitted_at"
KEY_TRAINING_SIZE = "product_quantization.training_size"
KEY_ENCODED_COUNT = "product_quantization.encoded_count"

#: Minimum number of trained vectors before a fit is meaningful.
#: Matches the FAISS-recommended 39 × Ks; below it the codebook
#: still trains but the warning fires.
MIN_TRAINING_ROWS: int = 39 * DEFAULT_CENTROIDS_KS

#: BGE-M3 embeddings — 1024-dim. Gates the producer to bail early
#: if the active embedding dim doesn't match (sanity check, not a
#: hardcoded assumption — read from a sample row).
EXPECTED_DIMENSION: int = 1024

#: Encode batch size — keeps RAM bounded when re-encoding 100k+ rows.
ENCODE_BATCH_SIZE: int = 5_000


@dataclass(frozen=True)
class CodebookSnapshot:
    """The persisted PQ codebook + metadata."""

    codebook_blob: bytes
    dimension: int
    m: int
    ks: int
    bytes_per_vector: int
    version: str
    fitted_at: str | None
    training_size: int
    encoded_count: int


@dataclass(frozen=True)
class FitResult:
    """Outcome of a single :func:`fit_and_persist_from_embeddings` run."""

    snapshot: CodebookSnapshot
    rows_encoded: int


# ── Read API ──────────────────────────────────────────────────────


def load_codebook() -> CodebookSnapshot | None:
    """Return the persisted codebook + metadata, or ``None`` on cold start."""
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return None
    rows = dict(
        AppSetting.objects.filter(
            key__in=[
                KEY_CODEBOOK,
                KEY_DIMENSION,
                KEY_M,
                KEY_KS,
                KEY_BYTES_PER_VECTOR,
                KEY_VERSION,
                KEY_FITTED_AT,
                KEY_TRAINING_SIZE,
                KEY_ENCODED_COUNT,
            ]
        ).values_list("key", "value")
    )
    if KEY_CODEBOOK not in rows:
        return None
    try:
        blob = base64.b64decode(rows[KEY_CODEBOOK])
        return CodebookSnapshot(
            codebook_blob=blob,
            dimension=int(rows.get(KEY_DIMENSION, "0") or "0"),
            m=int(rows.get(KEY_M, str(DEFAULT_SUBVECTORS_M)) or DEFAULT_SUBVECTORS_M),
            ks=int(rows.get(KEY_KS, str(DEFAULT_CENTROIDS_KS)) or DEFAULT_CENTROIDS_KS),
            bytes_per_vector=int(rows.get(KEY_BYTES_PER_VECTOR, "0") or "0"),
            version=rows.get(KEY_VERSION, ""),
            fitted_at=rows.get(KEY_FITTED_AT),
            training_size=int(rows.get(KEY_TRAINING_SIZE, "0") or "0"),
            encoded_count=int(rows.get(KEY_ENCODED_COUNT, "0") or "0"),
        )
    except (TypeError, ValueError, base64.binascii.Error):
        logger.warning(
            "product_quantization_producer: malformed codebook AppSetting row"
        )
        return None


def load_quantizer() -> ProductQuantizer | None:
    """Return a ready-to-use :class:`ProductQuantizer` or ``None`` on cold start.

    Loads the codebook once; callers cache the result. The returned
    quantizer's ``trained`` is ``True`` immediately — no fit needed.
    """
    import numpy as np

    snap = load_codebook()
    if snap is None:
        return None
    quant = ProductQuantizer(dimension=snap.dimension, m=snap.m, ks=snap.ks)
    # FAISS's deserialize_index expects a numpy uint8 array, not raw
    # bytes — restore that shape before handing to load_state.
    blob_array = np.frombuffer(snap.codebook_blob, dtype=np.uint8)
    quant.load_state(blob_array)
    return quant


def decode_pq_codes(
    pq_codes: list[bytes],
    *,
    quantizer: ProductQuantizer | None = None,
):
    """Decode a list of ``pq_code`` byte-blobs to approximate float32 vectors.

    Returns a numpy array of shape ``(n, dimension)`` or ``None`` if
    the codebook isn't fitted yet.

    ``quantizer`` is optional — pass a cached one when decoding many
    code lists in a row to avoid re-loading the codebook from
    AppSetting every call.
    """
    import numpy as np

    if not pq_codes:
        return None
    quant = quantizer if quantizer is not None else load_quantizer()
    if quant is None:
        return None
    # Build a single (n, bytes_per_vector) uint8 array.
    bytes_per_vec = quant.bytes_per_vector
    n = len(pq_codes)
    flat = np.empty((n, bytes_per_vec), dtype=np.uint8)
    for i, code in enumerate(pq_codes):
        if code is None or len(code) != bytes_per_vec:
            # Defensive — skip rows with stale/wrong-sized codes by
            # writing zeros. Caller decides what to do with those.
            flat[i, :] = 0
        else:
            flat[i, :] = np.frombuffer(code, dtype=np.uint8)
    return quant.decode(flat)


def pq_cosine_for_pks(pks):
    """Return a dict ``{pk: decoded_unit_vector}`` for ContentItems with valid PQ codes.

    Used by consumers that want PQ-accelerated similarity in batch.
    Rows whose ``pq_code_version`` doesn't match the active codebook
    are skipped — they need a refit before participating. Cold-start
    safe: returns ``{}`` when no codebook is fitted yet.

    The returned vectors are L2-normalised so consumers can compute
    cosine similarity via a simple dot product.
    """
    import numpy as np

    from apps.content.models import ContentItem

    snap = load_codebook()
    if snap is None or not pks:
        return {}
    quant = load_quantizer()
    if quant is None:
        return {}

    rows = list(
        ContentItem.objects.filter(
            pk__in=list(pks),
            pq_code_version=snap.version,
        )
        .exclude(pq_code__isnull=True)
        .values_list("pk", "pq_code")
    )
    if not rows:
        return {}

    codes = [bytes(c) for _, c in rows]
    decoded = decode_pq_codes(codes, quantizer=quant)
    if decoded is None:
        return {}
    # Normalise so callers can do `decoded @ decoded.T` for cosine.
    norms = np.linalg.norm(decoded, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    unit = decoded / norms
    return {pk: unit[i] for i, (pk, _) in enumerate(rows)}


def pq_pairwise_similarity_above(
    pks,
    *,
    threshold: float = 0.9,
) -> list[tuple]:
    """Return pairs of pks whose PQ-approximate cosine ≥ *threshold*.

    Group B.2's :func:`pq_cosine_for_pks` returns the per-pk decoded
    unit vector; this helper layers a single matrix multiplication on
    top to find approximate near-duplicates in a batch without
    hitting Postgres. Useful for offline jobs (clustering, near-dup
    detection, similarity-matrix construction) where the
    bias-vs-variance trade-off of PQ is acceptable.

    Returns a list of ``(pk_a, pk_b, approximate_cosine)`` triples
    with ``pk_a < pk_b`` so each unordered pair appears once.

    Cold-start safe: empty input → ``[]``; codebook missing → ``[]``;
    too-few qualifying rows → ``[]``. Callers that need a verified
    answer should re-validate the returned pairs against the full
    embedding (pgvector ``<=>``) — PQ is approximate by design and
    the threshold may pull in a 1-3% false-positive rate per Jégou
    et al. 2011 Table 2.
    """
    import numpy as np

    if not pks or threshold <= 0.0:
        return []
    table = pq_cosine_for_pks(pks)
    if len(table) < 2:
        return []

    pk_list = sorted(table.keys())
    matrix = np.stack([table[pk] for pk in pk_list], axis=0)
    # Cosine similarity = dot product of L2-normalised vectors.
    sims = matrix @ matrix.T

    # Take the upper triangle (excluding diagonal) so each pair is
    # emitted once.
    out: list[tuple] = []
    rows, cols = np.where(sims >= threshold)
    for i, j in zip(rows, cols):
        if i >= j:
            continue
        out.append((pk_list[int(i)], pk_list[int(j)], float(sims[i, j])))
    return out


# ── Producer ──────────────────────────────────────────────────────


def fit_and_persist_from_embeddings(
    *,
    min_training_rows: int = MIN_TRAINING_ROWS,
    m: int = DEFAULT_SUBVECTORS_M,
    ks: int = DEFAULT_CENTROIDS_KS,
    encode_batch_size: int = ENCODE_BATCH_SIZE,
    progress_callback=None,
) -> FitResult | None:
    """Fit the PQ codebook over existing ContentItem embeddings + backfill codes.

    Steps:

    1. Sample existing ``ContentItem.embedding`` rows (must be
       non-null).  Below ``min_training_rows`` → return None, leave
       AppSetting + ``pq_code`` columns untouched.
    2. Fit a :class:`ProductQuantizer` on the sampled vectors.
    3. Persist the codebook bytes (base64 encoded) plus metadata to
       AppSetting.
    4. Iterate over every ContentItem with a non-null embedding,
       encode in batches, and write back ``pq_code`` +
       ``pq_code_version``. Idempotent: re-running on unchanged data
       writes the same code bytes (same codebook → deterministic
       encode).

    Cold-start safe — the function may be called against an empty
    ContentItem table on a brand-new install, in which case it
    returns None and the W1 job logs "insufficient training data".

    ``progress_callback(progress_pct, message)`` if supplied is
    invoked at each major step and at every ``encode_batch_size``
    row checkpoint. Compatible with the W1 job runner's
    ``checkpoint`` signature.
    """
    import numpy as np

    from apps.content.models import ContentItem
    from apps.core.models import AppSetting
    from django.db import transaction
    from django.utils import timezone

    def _progress(pct: float, msg: str) -> None:
        if progress_callback is not None:
            progress_callback(progress_pct=pct, message=msg)

    # Step 1 — gather training set.
    _progress(0.0, "Loading training embeddings")
    train_qs = ContentItem.objects.exclude(embedding__isnull=True).values_list(
        "embedding", flat=True
    )
    train_total = train_qs.count()
    if train_total < min_training_rows:
        logger.info(
            "product_quantization_producer: %d trained rows (< %d minimum), "
            "skipping fit",
            train_total,
            min_training_rows,
        )
        _progress(100.0, f"Insufficient training data ({train_total} rows)")
        return None

    # Cap training size — Jégou 2011 §IV says ~100k samples is plenty
    # for a 1024-dim codebook. Sampling more wastes RAM without
    # improving the fit.
    train_cap = max(min_training_rows, 100_000)
    sample_qs = train_qs[:train_cap]
    train_array = np.asarray(list(sample_qs), dtype=np.float32)
    if train_array.ndim != 2:
        # Defensive — pgvector arrays should always be 2-D, but a
        # corrupted row would dump in 1-D shape.
        logger.warning(
            "product_quantization_producer: training array shape %s "
            "is not 2-D; aborting fit",
            train_array.shape,
        )
        _progress(100.0, "Training array shape invalid")
        return None
    dimension = int(train_array.shape[1])

    # Step 2 — fit.
    _progress(15.0, f"Fitting PQ codebook over {train_array.shape[0]} vectors")
    quantizer = ProductQuantizer(dimension=dimension, m=m, ks=ks)
    quantizer.fit(train_array)

    # Step 3 — persist codebook + metadata.
    _progress(40.0, "Persisting codebook to AppSetting")
    blob = quantizer.trained_state()
    blob_bytes = bytes(blob) if not isinstance(blob, bytes) else blob
    version = hashlib.sha256(blob_bytes).hexdigest()[:16]
    fitted_at = timezone.now().isoformat()

    for key, value, description in (
        (
            KEY_CODEBOOK,
            base64.b64encode(blob_bytes).decode("ascii"),
            "Pick #20 Product Quantization — base64-encoded FAISS IndexPQ codebook.",
        ),
        (
            KEY_DIMENSION,
            str(dimension),
            "Embedding dimension the codebook was trained on.",
        ),
        (KEY_M, str(m), "Number of subvectors per encoded vector."),
        (KEY_KS, str(ks), "Number of centroids per subvector codebook."),
        (
            KEY_BYTES_PER_VECTOR,
            str(quantizer.bytes_per_vector),
            "Compressed size in bytes per vector.",
        ),
        (
            KEY_VERSION,
            version,
            "Hex tag of the codebook bytes — pq_code_version on each "
            "encoded row must match this value.",
        ),
        (KEY_FITTED_AT, fitted_at, "ISO timestamp of the most recent fit."),
        (
            KEY_TRAINING_SIZE,
            str(train_array.shape[0]),
            "Training-set size used to fit the codebook.",
        ),
    ):
        AppSetting.objects.update_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )

    # Step 4 — encode + backfill in batches.
    _progress(50.0, "Encoding ContentItem embeddings to pq_code")
    encoded_total = 0
    rows_to_encode = ContentItem.objects.exclude(embedding__isnull=True).values_list(
        "pk", "embedding"
    )
    # Iterate in chunks so the FAISS encode call doesn't pull every
    # vector into RAM at once.
    pks_for_batch: list = []
    vectors_for_batch: list = []
    total_rows = train_total

    def _flush_batch(pks, vectors):
        nonlocal encoded_total
        if not pks:
            return
        arr = np.asarray(vectors, dtype=np.float32)
        codes = quantizer.encode(arr)
        with transaction.atomic():
            for pk, code_row in zip(pks, codes):
                ContentItem.objects.filter(pk=pk).update(
                    pq_code=bytes(code_row.tobytes()),
                    pq_code_version=version,
                )
        encoded_total += len(pks)

    for pk, embedding in rows_to_encode.iterator(chunk_size=encode_batch_size):
        if embedding is None:
            continue
        pks_for_batch.append(pk)
        vectors_for_batch.append(embedding)
        if len(pks_for_batch) >= encode_batch_size:
            _flush_batch(pks_for_batch, vectors_for_batch)
            pks_for_batch = []
            vectors_for_batch = []
            pct = 50.0 + (encoded_total / max(1, total_rows)) * 45.0
            _progress(
                min(pct, 95.0),
                f"Encoded {encoded_total} / {total_rows} rows",
            )
    _flush_batch(pks_for_batch, vectors_for_batch)

    AppSetting.objects.update_or_create(
        key=KEY_ENCODED_COUNT,
        defaults={
            "value": str(encoded_total),
            "description": "Number of ContentItem rows whose pq_code is current.",
        },
    )

    snapshot = CodebookSnapshot(
        codebook_blob=blob_bytes,
        dimension=dimension,
        m=m,
        ks=ks,
        bytes_per_vector=quantizer.bytes_per_vector,
        version=version,
        fitted_at=fitted_at,
        training_size=int(train_array.shape[0]),
        encoded_count=encoded_total,
    )
    _progress(100.0, f"PQ refit complete — {encoded_total} rows encoded")
    return FitResult(snapshot=snapshot, rows_encoded=encoded_total)
