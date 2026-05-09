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

    Tries the safe V2 npz format first; falls back to the deprecated V1
    pickle format for backwards compatibility (logs a deprecation warning).
    """
    global _MODEL_CACHE
    if not HAS_BPR:
        return _EMPTY
    path = _read_path()
    if not path or not os.path.exists(path):
        return _EMPTY
    if _MODEL_CACHE is not None and _MODEL_CACHE[0] == path:
        return _MODEL_CACHE[1]
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

    # V2 format (2026-05-09): write factor arrays via numpy.savez_compressed,
    # indexes as JSON inside the same archive. No pickle anywhere on the
    # save path. Old V1 pickled snapshots remain readable via the
    # _load_v1_legacy_pickle fallback for one release.
    #
    # Pass a file handle (not a path string) so numpy doesn't auto-append
    # ".npz" — operator's configured path is honoured exactly.
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as fh:
        np.savez_compressed(
            fh,
            user_factors=np.asarray(model.user_factors, dtype=np.float32),
            item_factors=np.asarray(model.item_factors, dtype=np.float32),
            # numpy arrays don't natively hold dicts, so we store the
            # indexes as JSON-encoded byte arrays. ``np.load`` reads them
            # back as 0-d numpy arrays of bytes — see _load_v2_npz.
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
