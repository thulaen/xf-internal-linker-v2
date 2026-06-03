"""BPR (Bayesian Personalized Ranking) — pick #38.

Reference
---------
Rendle, S., Freudenthaler, C., Gantner, Z., & Schmidt-Thieme, L.
(2009). "BPR: Bayesian Personalized Ranking from Implicit Feedback."
*Proceedings of UAI 2009*, pp. 452-461.

Goal
----
BPR is a pairwise ranking loss for implicit feedback. Given click /
approve events, it learns user-item embeddings such that
``score(user, clicked) > score(user, not_clicked)`` is satisfied
on more pairs than chance. For the linker, this becomes a
"destination latent factor" feature — destinations clicked across
many similar review-queue contexts cluster in latent space.

Wraps the ``implicit`` PyPI package (which has a fast Cython BPR
implementation). Cold-start safe: missing pip dep → no-op trainer
+ ``score_for_user`` returns ``None``.
"""

from __future__ import annotations

import io
import json
import logging
import os
import pickle
from dataclasses import dataclass, field

import numpy as np

try:
    import implicit  # noqa: F401
    from implicit.bpr import BayesianPersonalizedRanking as _BPR
    from scipy.sparse import csr_matrix as _csr_matrix

    HAS_BPR = True
except ImportError:  # pragma: no cover — depends on pip env
    _BPR = None  # type: ignore[assignment]
    _csr_matrix = None  # type: ignore[assignment]
    HAS_BPR = False


logger = logging.getLogger(__name__)


KEY_MODEL_PATH = "bpr.model_path"

#: Rendle et al. §5 default factor count. 50 keeps the model
#: small enough to live in memory; >100 helps when the user × item
#: matrix is dense, which our review queue isn't.
DEFAULT_FACTORS: int = 50
DEFAULT_ITERATIONS: int = 100
DEFAULT_LEARNING_RATE: float = 0.01
DEFAULT_REGULARIZATION: float = 0.01


@dataclass(frozen=True)
class BPRSnapshot:
    """Persisted BPR model + the index→user/item maps.

    Format V2 (2026-05-09): the trained user/item factor matrices are
    stored directly as numpy arrays (``user_factors`` / ``item_factors``).
    Inference reads them straight off the snapshot — no pickle.

    Legacy V1: ``model_blob`` held a pickled
    ``implicit.bpr.BayesianPersonalizedRanking`` object. Loading it
    required ``pickle.loads`` which is an arbitrary-code-execution
    risk if the on-disk file (or DB blob) is tampered with. Kept as a
    fallback for ONE release so existing snapshots keep working until
    the next training run produces a V2 file. Logged with a warning so
    the operator can see the legacy path is in use.
    """

    user_index: dict[str, int]
    item_index: dict[str, int]
    factors: int
    # V2 fields — populated by ``_load_npz``. ``None`` means a legacy
    # snapshot that still needs the pickle fallback.
    user_factors: np.ndarray | None = None
    item_factors: np.ndarray | None = None
    # V1 legacy field — populated only by the pickle fallback path.
    model_blob: bytes = b""

    @property
    def is_empty(self) -> bool:
        return not self.user_index or not self.item_index


_EMPTY = BPRSnapshot(user_index={}, item_index={}, factors=0)
_MODEL_CACHE: tuple[str, BPRSnapshot, object] | None = None


def is_available() -> bool:
    """True when ``implicit`` is importable."""
    return HAS_BPR


def _read_path() -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=KEY_MODEL_PATH).first()
    except Exception:  # noqa: BLE001  # AppSetting unavailable (cold-start); empty path makes the loader treat the model as "not yet trained" and return _EMPTY.
        return ""
    return (row.value if row else "") or ""


def _load_v2_npz(path: str) -> BPRSnapshot | None:
    """Try to load a V2 (numpy-savez) snapshot from *path*.

    Returns ``None`` if the file isn't an npz archive (the loader will
    fall back to the legacy pickle path). Never raises — failure
    returns ``None`` and logs a debug message.
    """
    try:
        with np.load(path, allow_pickle=False) as archive:
            user_factors = np.asarray(archive["user_factors"], dtype=np.float32)
            item_factors = np.asarray(archive["item_factors"], dtype=np.float32)
            user_index_json = bytes(archive["user_index_json"]).decode("utf-8")
            item_index_json = bytes(archive["item_index_json"]).decode("utf-8")
            factors = int(archive["factors"])
        return BPRSnapshot(
            user_index=json.loads(user_index_json),
            item_index=json.loads(item_index_json),
            factors=factors,
            user_factors=user_factors,
            item_factors=item_factors,
        )
    except Exception:
        # Not an npz archive (or it's corrupt). The caller will try the
        # legacy pickle path next.
        logger.debug("bpr_ranking: V2 npz load failed for %s", path, exc_info=True)
        return None


def _parquet_companion_path(path: str) -> str:
    """Map the configured BPR model path to its Parquet sidecar location.

    ``model.pkl`` → ``model.parquet``. Keeps the AppSetting pointing at the
    historical npz/pickle path while we migrate the on-disk format.
    """
    from pathlib import Path

    p = Path(path)
    if p.suffix.lower() == ".parquet":
        return str(p)
    return str(p.with_suffix(".parquet"))


def _build_bpr_v3_rows(
    *,
    user_factors: np.ndarray,
    item_factors: np.ndarray,
    user_index: dict[str, int],
    item_index: dict[str, int],
    factors: int,
) -> dict[str, list]:
    """Flatten the BPR snapshot into the four parallel column lists used by V3.

    The result feeds straight into ``pl.DataFrame(...)`` with the long-form
    Parquet schema (entity_kind, entity_id, idx, vector).
    """
    user_rows = [
        (
            "user",
            str(user_id),
            int(idx),
            np.asarray(user_factors[idx], dtype=np.float32).astype(float).tolist(),
        )
        for user_id, idx in user_index.items()
    ]
    item_rows = [
        (
            "item",
            str(item_id),
            int(idx),
            np.asarray(item_factors[idx], dtype=np.float32).astype(float).tolist(),
        )
        for item_id, idx in item_index.items()
    ]
    rows = [("meta", "factors", 0, [float(factors)]), *user_rows, *item_rows]
    kinds = [row[0] for row in rows]
    ids = [row[1] for row in rows]
    idxs = [row[2] for row in rows]
    vecs = [row[3] for row in rows]
    return {"entity_kind": kinds, "entity_id": ids, "idx": idxs, "vector": vecs}


def _save_v3_parquet(
    path: str,
    *,
    user_factors: np.ndarray,
    item_factors: np.ndarray,
    user_index: dict[str, int],
    item_index: dict[str, int],
    factors: int,
) -> bool:
    """Write the BPR snapshot as a single Parquet file. Atomic via tmp + rename.

    Schema: entity_kind (Utf8), entity_id (Utf8), idx (Int64), vector (List[Float32]).
    The ``factors`` count is stored as a meta-row (entity_kind="meta", entity_id="factors").
    Returns False if Polars is unavailable; caller falls back to V2 npz.
    """
    try:
        import polars as pl

        from apps.pipeline.services._parquet_io import write_parquet_atomic
    except ImportError:
        logger.debug("Polars or _parquet_io missing — falling back to V2 npz")
        return False
    try:
        columns = _build_bpr_v3_rows(
            user_factors=user_factors,
            item_factors=item_factors,
            user_index=user_index,
            item_index=item_index,
            factors=factors,
        )
        df = pl.DataFrame(
            columns,
            schema={
                "entity_kind": pl.Utf8,
                "entity_id": pl.Utf8,
                "idx": pl.Int64,
                "vector": pl.List(pl.Float32),
            },
        )
        n = len(columns["entity_kind"])
        write_parquet_atomic(df, path, estimated_bytes=max(1, n) * factors * 5)
        return True
    except Exception as exc:  # noqa: BLE001 — Parquet write failed; caller falls back to V2 npz.
        logger.warning("bpr_ranking: V3 Parquet write failed at %s: %s", path, exc)
        return False


def _load_v3_parquet(path: str) -> BPRSnapshot | None:
    """Try to load a V3 (Polars Parquet) snapshot.

    Returns None if the file is missing or fails to parse. The caller will
    cascade to V2 npz, then V1 pickle.
    """
    if not os.path.exists(path):
        return None
    try:
        import polars as pl

        df = pl.read_parquet(path)
        meta = df.filter(pl.col("entity_kind") == "meta").to_dicts()
        factors = DEFAULT_FACTORS
        for row in meta:
            if row.get("entity_id") == "factors":
                vector = row.get("vector") or []
                if vector:
                    factors = int(vector[0])
                break

        user_rows = df.filter(pl.col("entity_kind") == "user").sort("idx").to_dicts()
        item_rows = df.filter(pl.col("entity_kind") == "item").sort("idx").to_dicts()

        user_index = {str(r["entity_id"]): int(r["idx"]) for r in user_rows}
        item_index = {str(r["entity_id"]): int(r["idx"]) for r in item_rows}

        if user_rows:
            user_factors = np.asarray(
                [r["vector"] for r in user_rows], dtype=np.float32
            )
        else:
            user_factors = np.zeros((0, factors), dtype=np.float32)
        if item_rows:
            item_factors = np.asarray(
                [r["vector"] for r in item_rows], dtype=np.float32
            )
        else:
            item_factors = np.zeros((0, factors), dtype=np.float32)

        return BPRSnapshot(
            user_index=user_index,
            item_index=item_index,
            factors=factors,
            user_factors=user_factors,
            item_factors=item_factors,
        )
    except Exception as exc:  # noqa: BLE001 — V3 read failed; cascade to V2.
        logger.warning("bpr_ranking: V3 Parquet load failed at %s: %s", path, exc)
        return None


def _load_v1_legacy_pickle(path: str) -> BPRSnapshot | None:
    """Fallback for legacy pickled snapshots produced before 2026-05-09.

    Logs a WARNING — operator should retrain to produce a V2 file.
    Will be removed one release after the V2 format ships.
    """
    try:
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
        logger.warning(
            "bpr_ranking: loading LEGACY pickle snapshot from %s — retrain "
            "via fit_and_save() to upgrade to the safe V2 format. The "
            "legacy path is a pickle.loads RCE vector if the file is "
            "tampered with; remove the file and retrain at your earliest "
            "convenience.",
            path,
        )
        return BPRSnapshot(
            model_blob=payload.get("model_blob", b""),
            user_index=dict(payload.get("user_index", {})),
            item_index=dict(payload.get("item_index", {})),
            factors=int(payload.get("factors", DEFAULT_FACTORS)),
        )
    except Exception as exc:
        logger.warning("bpr_ranking: legacy pickle load failed: %s", exc)
        return None


def load_snapshot() -> BPRSnapshot:
    """Return the persisted snapshot or :data:`_EMPTY` on cold start.

    Tries V3 (Parquet) first, then V2 (npz), then the deprecated V1 pickle
    format for backwards compatibility. Each cascade step logs a warning so
    operators can see which format is active.
    """
    global _MODEL_CACHE
    if not HAS_BPR:
        return _EMPTY
    path = _read_path()
    if not path:
        return _EMPTY
    if _MODEL_CACHE is not None and _MODEL_CACHE[0] == path:
        return _MODEL_CACHE[1]

    parquet_path = _parquet_companion_path(path)
    snap: BPRSnapshot | None = _load_v3_parquet(parquet_path)
    if snap is None and os.path.exists(path):
        snap = _load_v2_npz(path) or _load_v1_legacy_pickle(path)
    if snap is None:
        return _EMPTY
    _MODEL_CACHE = (path, snap, None)
    return snap


def score_for_user(user_id: str, item_ids: list[str]) -> dict[str, float] | None:
    """Score *item_ids* for a single *user_id*.

    Cold-start safe: missing dep / no model / toggle off → ``None``.
    Items the model hasn't seen yet aren't in the output.
    """
    from apps.core.runtime_flags import is_enabled

    if not is_enabled("bpr.enabled", default=True):
        return None
    snap = load_snapshot()
    if snap.is_empty:
        return None
    user_idx = snap.user_index.get(str(user_id))
    if user_idx is None:
        return None

    # V2 path: snap holds user_factors / item_factors directly. No
    # pickle.loads needed. This is the safe default for all snapshots
    # written after 2026-05-09.
    if snap.user_factors is not None and snap.item_factors is not None:
        user_factors = snap.user_factors
        item_factors = snap.item_factors
    else:
        # V1 legacy path: snap.model_blob is a pickled
        # implicit.bpr model. Falls back to pickle.loads with an
        # already-logged deprecation warning from load_snapshot.
        # Cache the unpickled model alongside the snapshot.
        global _MODEL_CACHE
        if _MODEL_CACHE is None or _MODEL_CACHE[2] is None:
            try:
                model = pickle.loads(snap.model_blob)  # noqa: S301 — legacy fallback only, will be removed after one release; load path logs a deprecation warning
                _MODEL_CACHE = (_read_path(), snap, model)
            except Exception as exc:
                logger.warning("bpr_ranking: legacy model unpickle failed: %s", exc)
                return None
        _, _, model = _MODEL_CACHE
        user_factors = model.user_factors
        item_factors = model.item_factors

    out: dict[str, float] = {}
    for item in item_ids:
        idx = snap.item_index.get(str(item))
        if idx is None:
            continue
        try:
            score = float(user_factors[user_idx] @ item_factors[idx])
        except Exception:  # noqa: BLE001  # Per-item dot product can fail on shape mismatch (model retrained but caller cached old item_index); skip the item rather than poison the whole user's score map.
            continue
        out[item] = score
    return out


def fit_and_save(
    interactions: list[tuple[str, str, float]],
    *,
    output_path: str,
    factors: int = DEFAULT_FACTORS,
    iterations: int = DEFAULT_ITERATIONS,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    regularization: float = DEFAULT_REGULARIZATION,
) -> bool:
    """Train BPR on (user_id, item_id, weight) triples; persist.

    Returns True on success. Cold-start safe at every layer.
    """
    if not HAS_BPR:
        logger.info("bpr_ranking.fit_and_save: implicit not installed")
        return False
    if len(interactions) < 5:
        return False

    user_index: dict[str, int] = {}
    item_index: dict[str, int] = {}
    rows: list[int] = []
    cols: list[int] = []
    weights: list[float] = []
    for user, item, weight in interactions:
        u_key = str(user)
        i_key = str(item)
        user_idx = user_index.setdefault(u_key, len(user_index))
        item_idx = item_index.setdefault(i_key, len(item_index))
        rows.append(user_idx)
        cols.append(item_idx)
        weights.append(float(weight))
    matrix = _csr_matrix(
        (weights, (rows, cols)),
        shape=(len(user_index), len(item_index)),
    )
    try:
        model = _BPR(
            factors=factors,
            iterations=iterations,
            learning_rate=learning_rate,
            regularization=regularization,
        )
        model.fit(matrix)
    except Exception as exc:
        logger.warning("bpr_ranking.fit_and_save train failed: %s", exc)
        return False

    # V3 format (2026-05-09): single Parquet file at <path>.parquet. No pickle.
    # Falls back to V2 npz at the original path if Polars is unavailable, so a
    # broken Polars install never loses a refit. V1 pickle snapshots remain
    # readable via the legacy load path for one release.
    user_factors_arr = np.asarray(model.user_factors, dtype=np.float32)
    item_factors_arr = np.asarray(model.item_factors, dtype=np.float32)
    parquet_path = _parquet_companion_path(output_path)
    saved_v3 = _save_v3_parquet(
        parquet_path,
        user_factors=user_factors_arr,
        item_factors=item_factors_arr,
        user_index=user_index,
        item_index=item_index,
        factors=factors,
    )
    if not saved_v3:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as fh:
            np.savez_compressed(
                fh,
                user_factors=user_factors_arr,
                item_factors=item_factors_arr,
                user_index_json=np.frombuffer(
                    json.dumps(user_index).encode("utf-8"), dtype=np.uint8
                ),
                item_index_json=np.frombuffer(
                    json.dumps(item_index).encode("utf-8"), dtype=np.uint8
                ),
                factors=np.int32(factors),
            )
    global _MODEL_CACHE
    _MODEL_CACHE = None
    return True
