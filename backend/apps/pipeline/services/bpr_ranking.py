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

import logging
import os
import pickle
from dataclasses import dataclass

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
    """Persisted BPR model + the index→user/item maps."""

    model_blob: bytes
    user_index: dict[str, int]
    item_index: dict[str, int]
    factors: int

    @property
    def is_empty(self) -> bool:
        return not self.user_index or not self.item_index


_EMPTY = BPRSnapshot(model_blob=b"", user_index={}, item_index={}, factors=0)
_MODEL_CACHE: tuple[str, BPRSnapshot, object] | None = None


def is_available() -> bool:
    """True when ``implicit`` is importable."""
    return HAS_BPR


def _read_path() -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=KEY_MODEL_PATH).first()
    except Exception:
        return ""
    return (row.value if row else "") or ""


def load_snapshot() -> BPRSnapshot:
    """Return the persisted snapshot or :data:`_EMPTY` on cold start."""
    global _MODEL_CACHE
    if not HAS_BPR:
        return _EMPTY
    path = _read_path()
    if not path or not os.path.exists(path):
        return _EMPTY
    if _MODEL_CACHE is not None and _MODEL_CACHE[0] == path:
        return _MODEL_CACHE[1]
    try:
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
    except Exception as exc:
        logger.warning("bpr_ranking: load failed: %s", exc)
        return _EMPTY
    snap = BPRSnapshot(
        model_blob=payload.get("model_blob", b""),
        user_index=dict(payload.get("user_index", {})),
        item_index=dict(payload.get("item_index", {})),
        factors=int(payload.get("factors", DEFAULT_FACTORS)),
    )
    _MODEL_CACHE = (path, snap, None)
    return snap


def score_for_user(user_id: str, item_ids: list[str]) -> dict[str, float] | None:
    """Score *item_ids* for a single *user_id*.

    Cold-start safe: missing dep / no model → ``None``. Items the
    model hasn't seen yet aren't in the output.
    """
    snap = load_snapshot()
    if snap.is_empty:
        return None
    user_idx = snap.user_index.get(str(user_id))
    if user_idx is None:
        return None

    # Lazy-load the trained model object (heavy) only when actually
    # scoring. Cache it alongside the snapshot.
    global _MODEL_CACHE
    if _MODEL_CACHE is None or _MODEL_CACHE[2] is None:
        try:
            model = pickle.loads(snap.model_blob)
            _MODEL_CACHE = (
                _read_path(),
                snap,
                model,
            )
        except Exception as exc:
            logger.warning("bpr_ranking: model unpickle failed: %s", exc)
            return None
    _, _, model = _MODEL_CACHE
    out: dict[str, float] = {}
    for item in item_ids:
        idx = snap.item_index.get(str(item))
        if idx is None:
            continue
        try:
            score = float(
                model.user_factors[user_idx] @ model.item_factors[idx]
            )
        except Exception:
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

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as fh:
        pickle.dump(
            {
                "model_blob": pickle.dumps(model),
                "user_index": user_index,
                "item_index": item_index,
                "factors": factors,
            },
            fh,
            protocol=4,
        )
    global _MODEL_CACHE
    _MODEL_CACHE = None
    return True
