"""Factorization Machines — pick #39 (hand-rolled NumPy).

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

Why hand-rolled and not a pip dep
---------------------------------
The libFM family (pyfm, pylibfm, fastFM) all stalled on Python ≤
3.11 builds. Rather than pin a brittle dep, we ship Rendle 2010
§3.1 eq. 1-3 in pure NumPy. ~80 lines, deterministic, no Cython
build, no version drift.

The trainer uses SGD with a constant learning rate (paper §3.3
"online updates") on a logistic objective for binary targets and
MSE for regression. Categorical features are handled by the same
DictVectorizer the previous wrapper used so the call surface is
unchanged.

Cold-start safe end-to-end:
- Empty input → ``[]``.
- ``predict`` on un-fitted model → ``None`` (caller branches on
  missing-signal).
- AppSetting model_path empty / file missing → ``predict`` → ``None``.
"""

from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass

import numpy as np

try:
    from sklearn.feature_extraction import DictVectorizer as _DictVectorizer

    HAS_SKLEARN = True
except ImportError:  # pragma: no cover — sklearn is in requirements.txt
    _DictVectorizer = None  # type: ignore[assignment]
    HAS_SKLEARN = False


logger = logging.getLogger(__name__)


KEY_MODEL_PATH = "factorization_machines.model_path"

#: Rendle 2010 §3.1 default factor count. 8 keeps the latent vector
#: tiny — fine for our small feature space.
DEFAULT_FACTORS: int = 8
DEFAULT_NUM_ITER: int = 50
DEFAULT_LEARNING_RATE: float = 0.001
#: L2 regularisation on weights and factors. Rendle §3.3
#: "regularisation prevents overfitting on small datasets".
DEFAULT_REGULARIZATION: float = 0.001


@dataclass
class _FmModel:
    """Hand-rolled FM weights — ``w0`` + linear + pairwise factors."""

    w0: float
    w: np.ndarray             # shape (n_features,)
    V: np.ndarray             # shape (n_features, factors)
    task: str                 # "regression" or "classification"

    def predict_one(self, x: np.ndarray) -> float:
        """Score a single feature row using Rendle eq. 5 (linear-time)."""
        # Pairwise interaction term computed in O(k·n) via the trick
        # from Rendle §3.2 eq. 5:
        #   Σ_f [ (Σ_i v_i,f * x_i)² − Σ_i v_i,f² * x_i² ] / 2
        Vx = self.V.T @ x          # shape (factors,)
        VxSq = (self.V.T ** 2) @ (x ** 2)
        pairwise = 0.5 * float(np.sum(Vx ** 2 - VxSq))
        linear = float(np.dot(self.w, x)) + self.w0
        raw = linear + pairwise
        if self.task == "classification":
            return float(1.0 / (1.0 + np.exp(-raw)))
        return float(raw)


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
_CACHE: tuple[str, _FmModel, object] | None = None  # (path, model, vectorizer)


def is_available() -> bool:
    """True when sklearn (DictVectorizer) is importable.

    NumPy is always available — we don't require any FM pip dep.
    """
    return HAS_SKLEARN


def _read_path() -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=KEY_MODEL_PATH).first()
    except Exception:
        return ""
    return (row.value if row else "") or ""


def load_snapshot() -> FMSnapshot:
    """Return the persisted snapshot or :data:`_EMPTY` on cold start."""
    if not HAS_SKLEARN:
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

    Cold-start safe: missing dep / no model → ``None`` (caller
    branches on missing-signal). Real-data ready once the model is
    trained.
    """
    if not features:
        return []
    from apps.core.runtime_flags import is_enabled

    if not is_enabled("factorization_machines.enabled", default=True):
        return None
    model, vectorizer = _load_model_and_vectorizer()
    if model is None or vectorizer is None:
        return None
    try:
        X = vectorizer.transform(features).toarray()
        return [model.predict_one(X[i]) for i in range(X.shape[0])]
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
    regularization: float = DEFAULT_REGULARIZATION,
    task: str = "regression",
    seed: int | None = 0,
) -> bool:
    """Train an FM on (features, target) pairs; persist.

    *features* is a list of feature-dicts (DictVectorizer-friendly).
    *targets* is a parallel list of floats. Cold-start safe.

    Implements Rendle 2010 §3.1 eq. 1-3 with SGD updates per §3.3.
    For binary classification (task="classification") we apply a
    sigmoid + cross-entropy loss; for regression we use MSE.
    """
    if not HAS_SKLEARN:
        logger.info("factorization_machines.fit_and_save: sklearn not installed")
        return False
    if len(features) < 5 or len(features) != len(targets):
        return False
    try:
        vectorizer = _DictVectorizer()
        X = vectorizer.fit_transform(features).toarray()
        y = np.asarray(targets, dtype=np.float64)
        n, d = X.shape

        rng = np.random.default_rng(seed)
        w0 = 0.0
        w = np.zeros(d, dtype=np.float64)
        V = rng.normal(scale=0.01, size=(d, factors))

        is_clf = task == "classification"

        for _ in range(num_iter):
            for i in range(n):
                xi = X[i]
                # Forward pass — Rendle eq. 5 trick.
                Vx = V.T @ xi
                pairwise = 0.5 * float(np.sum(Vx ** 2 - (V.T ** 2) @ (xi ** 2)))
                raw = w0 + float(np.dot(w, xi)) + pairwise
                if is_clf:
                    pred = 1.0 / (1.0 + np.exp(-raw))
                    grad = pred - y[i]
                else:
                    pred = raw
                    grad = pred - y[i]

                # Updates — paper §3.3.
                w0 -= learning_rate * (grad + regularization * w0)
                # Linear weights — only update parameters tied to
                # non-zero features (Rendle 2010 §3.2 eq. 4: gradient
                # for w_i is x_i, which is 0 for zero features).
                mask = xi != 0
                w[mask] -= learning_rate * (
                    grad * xi[mask] + regularization * w[mask]
                )
                # Latent factors — paper §3.2 eq. 6:
                # ∂pairwise / ∂v_{i,f} = x_i (Σ_j v_{j,f} x_j) − x_i² v_{i,f}
                # The x_i factor zeroes the gradient for zero
                # features, so we apply the same mask as the linear
                # weights — only updating active rows of V keeps the
                # update consistent with the linear path and avoids
                # spurious regularisation drift on inactive features.
                for f in range(factors):
                    sum_vfx = float(np.dot(V[:, f], xi))  # Σ_j v_{j,f} x_j
                    deriv_active = xi[mask] * sum_vfx - (
                        xi[mask] ** 2
                    ) * V[mask, f]
                    V[mask, f] -= learning_rate * (
                        grad * deriv_active + regularization * V[mask, f]
                    )

        model = _FmModel(w0=w0, w=w, V=V, task=task)
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
