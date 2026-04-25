"""Factorization Machines — pick #39.

Reference
---------
Rendle, S. (2010). "Factorization Machines." *2010 IEEE International
Conference on Data Mining (ICDM)*, pp. 995-1000.

Goal
----
FMs combine a linear model with low-rank pairwise feature
interactions:

    ŷ(x) = w0 + Σ_i w_i x_i + Σ_{i<j} <v_i, v_j> x_i x_j

For the linker, this gives the ranker a clean way to learn that
e.g. "destination_pagerank × host_topic_overlap" is more predictive
than either alone — without enumerating the cross-product manually.

Wraps the ``pyfm`` PyPI package (a Cython implementation of
``libFM``). Cold-start safe: missing pip dep → ``predict`` returns
``None`` for every input.
"""

from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass

try:
    from pyfm import pylibfm as _pyfm
    from sklearn.feature_extraction import DictVectorizer as _DictVectorizer
    from scipy.sparse import vstack as _vstack  # noqa: F401

    HAS_FM = True
except ImportError:  # pragma: no cover — depends on pip env
    _pyfm = None  # type: ignore[assignment]
    _DictVectorizer = None  # type: ignore[assignment]
    HAS_FM = False


logger = logging.getLogger(__name__)


KEY_MODEL_PATH = "factorization_machines.model_path"

#: Rendle 2010 §3 default factor count + epoch count. 8 factors
#: keeps the latent vector tiny — fine for our small feature space.
DEFAULT_FACTORS: int = 8
DEFAULT_NUM_ITER: int = 50
DEFAULT_LEARNING_RATE: float = 0.001


@dataclass(frozen=True)
class FMSnapshot:
    """Persisted FM model + DictVectorizer."""

    model_blob: bytes
    vectorizer_blob: bytes
    factors: int

    @property
    def is_empty(self) -> bool:
        return not self.model_blob


_EMPTY = FMSnapshot(model_blob=b"", vectorizer_blob=b"", factors=0)
_CACHE: tuple[str, object, object] | None = None  # (path, model, vectorizer)


def is_available() -> bool:
    """True when ``pyfm`` is importable."""
    return HAS_FM


def _read_path() -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=KEY_MODEL_PATH).first()
    except Exception:
        return ""
    return (row.value if row else "") or ""


def load_snapshot() -> FMSnapshot:
    """Return the persisted snapshot or :data:`_EMPTY` on cold start."""
    if not HAS_FM:
        return _EMPTY
    path = _read_path()
    if not path or not os.path.exists(path):
        return _EMPTY
    try:
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
    except Exception as exc:
        logger.warning("factorization_machines: load failed: %s", exc)
        return _EMPTY
    return FMSnapshot(
        model_blob=payload.get("model_blob", b""),
        vectorizer_blob=payload.get("vectorizer_blob", b""),
        factors=int(payload.get("factors", DEFAULT_FACTORS)),
    )


def _load_model_and_vectorizer():
    """Return ``(model, vectorizer)`` or ``(None, None)`` on cold start."""
    global _CACHE
    snap = load_snapshot()
    if snap.is_empty:
        return None, None
    path = _read_path()
    if _CACHE is not None and _CACHE[0] == path:
        return _CACHE[1], _CACHE[2]
    try:
        model = pickle.loads(snap.model_blob)
        vectorizer = pickle.loads(snap.vectorizer_blob)
    except Exception as exc:
        logger.warning("factorization_machines: unpickle failed: %s", exc)
        return None, None
    _CACHE = (path, model, vectorizer)
    return model, vectorizer


def predict(features: list[dict]) -> list[float] | None:
    """Score *features* (list of feature-dict per row).

    Cold-start safe: missing pip dep / no model → ``None`` (caller
    branches on missing-signal). Real-data ready once the model is
    trained.
    """
    if not features:
        return []
    model, vectorizer = _load_model_and_vectorizer()
    if model is None or vectorizer is None:
        return None
    try:
        X = vectorizer.transform(features)
        scores = model.predict(X)
        return [float(s) for s in scores]
    except Exception as exc:
        logger.warning("factorization_machines.predict failed: %s", exc)
        return None


def fit_and_save(
    features: list[dict],
    targets: list[float],
    *,
    output_path: str,
    factors: int = DEFAULT_FACTORS,
    num_iter: int = DEFAULT_NUM_ITER,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    task: str = "regression",
) -> bool:
    """Train an FM on (features, target) pairs; persist.

    *features* is a list of feature-dicts (DictVectorizer-friendly).
    *targets* is a parallel list of floats. Cold-start safe.
    """
    if not HAS_FM:
        logger.info("factorization_machines.fit_and_save: pyfm not installed")
        return False
    if len(features) < 5 or len(features) != len(targets):
        return False
    try:
        vectorizer = _DictVectorizer()
        X = vectorizer.fit_transform(features)
        model = _pyfm.FM(
            num_factors=factors,
            num_iter=num_iter,
            verbose=False,
            task=task,
            initial_learning_rate=learning_rate,
            learning_rate_schedule="optimal",
        )
        model.fit(X, targets)
    except Exception as exc:
        logger.warning("factorization_machines.fit_and_save train failed: %s", exc)
        return False

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as fh:
        pickle.dump(
            {
                "model_blob": pickle.dumps(model),
                "vectorizer_blob": pickle.dumps(vectorizer),
                "factors": factors,
            },
            fh,
            protocol=4,
        )
    global _CACHE
    _CACHE = None
    return True
