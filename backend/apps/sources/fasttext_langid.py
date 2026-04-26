"""FastText language identification — pick #14.

Reference
---------
Joulin, A., Grave, E., Bojanowski, P., Douze, M., Jégou, H., &
Mikolov, T. (2016). "FastText.zip: Compressing text classification
models." *arXiv:1612.03651*.

Joulin, A., Grave, E., Bojanowski, P., & Mikolov, T. (2016). "Bag of
Tricks for Efficient Text Classification." *Proceedings of the 15th
EACL*, pp. 427-431.

Goal
----
Detect the language of a text in 176 languages using the official
``lid.176.bin`` model (126 MB). Used to gate Stage-2 scoring (we
only link English ↔ English content) and to suppress non-English
content from the candidate pool.

Wraps the ``fasttext`` PyPI package. The model file lives at the
path read from AppSetting (``fasttext_langid.model_path``); when the
package isn't installed *or* the model file is missing, the helper
returns a neutral :class:`LangPrediction` with ``language="und"``
(undefined). Real-data ready — operators install the dep and place
``lid.176.bin`` at the configured path; subsequent calls auto-detect.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

try:
    import fasttext as _fasttext

    HAS_FASTTEXT = True
except ImportError:  # pragma: no cover — depends on pip env
    _fasttext = None  # type: ignore[assignment]
    HAS_FASTTEXT = False


logger = logging.getLogger(__name__)


#: Stand-in code for "undefined / cannot detect". Mirrors ICU's
#: ``und`` convention so consumers can compare against well-known
#: codes. Note: the lid.176 model itself emits ISO-639-1 (2-letter)
#: codes like ``en``, ``de``, ``fr`` — :class:`LangPrediction.language`
#: is ``UND`` only on failure / low-confidence.
UND_LANGUAGE: str = "und"

#: AppSetting key for the model path. Default ``""`` — operator must
#: install the model file and set this for real predictions.
KEY_MODEL_PATH: str = "fasttext_langid.model_path"

#: AppSetting key for the per-prediction confidence threshold below
#: which we return ``UND``. Joulin et al. report ~0.998 mean
#: confidence on clean inputs; 0.4 catches the noisy-input case
#: where the model is genuinely unsure.
KEY_MIN_CONFIDENCE: str = "fasttext_langid.min_confidence"
DEFAULT_MIN_CONFIDENCE: float = 0.4


@dataclass(frozen=True)
class LangPrediction:
    """One language-detection result."""

    language: str  # ISO 639-3 code (or UND_LANGUAGE on failure)
    confidence: float

    @property
    def is_undefined(self) -> bool:
        return self.language == UND_LANGUAGE


#: Returned when fastText is unavailable or the model isn't loaded.
UNDEFINED = LangPrediction(language=UND_LANGUAGE, confidence=0.0)


_MODEL_SINGLETON = None
_MODEL_PATH_LOADED: str | None = None


def is_available() -> bool:
    """True when the fasttext package is importable.

    Note this does **not** verify the model file is on disk — that
    check happens lazily on the first :func:`predict` call.
    """
    return HAS_FASTTEXT


def _load_model_path_from_settings() -> tuple[str, float]:
    """Read the model path + confidence threshold from AppSetting."""
    try:
        from apps.core.models import AppSetting

        path_row = AppSetting.objects.filter(key=KEY_MODEL_PATH).first()
        thresh_row = AppSetting.objects.filter(key=KEY_MIN_CONFIDENCE).first()
    except Exception:
        return "", DEFAULT_MIN_CONFIDENCE
    path = (path_row.value if path_row else "") or ""
    try:
        thresh = float(thresh_row.value) if thresh_row else DEFAULT_MIN_CONFIDENCE
    except (TypeError, ValueError):
        thresh = DEFAULT_MIN_CONFIDENCE
    return path, thresh


def _load_model(path: str):
    """Load and cache the fastText model from *path*."""
    global _MODEL_SINGLETON, _MODEL_PATH_LOADED
    if _MODEL_SINGLETON is not None and _MODEL_PATH_LOADED == path:
        return _MODEL_SINGLETON
    if not HAS_FASTTEXT or not path or not os.path.exists(path):
        return None
    try:
        _MODEL_SINGLETON = _fasttext.load_model(path)
        _MODEL_PATH_LOADED = path
        return _MODEL_SINGLETON
    except Exception as exc:
        logger.warning(
            "fasttext_langid: failed to load model at %s: %s",
            path,
            exc,
        )
        return None


def predict(text: str) -> LangPrediction:
    """Predict the language of *text* with fastText's lid.176.bin.

    Returns :data:`UNDEFINED` when:

    - The pip dep isn't installed.
    - The model file isn't on disk at the configured path.
    - The text is empty or whitespace.
    - The top prediction's confidence is below the threshold.

    Cold-start safe at every layer — the helper never raises on
    missing deps or missing models. Real-data ready: install the
    pip dep + set ``fasttext_langid.model_path`` and detection works.
    """
    if not text or not text.strip():
        return UNDEFINED
    if not HAS_FASTTEXT:
        return UNDEFINED
    from apps.core.runtime_flags import is_enabled

    if not is_enabled("fasttext_langid.enabled", default=True):
        return UNDEFINED
    path, threshold = _load_model_path_from_settings()
    model = _load_model(path)
    if model is None:
        return UNDEFINED
    # fasttext rejects multi-line input; collapse newlines.
    cleaned = " ".join(text.split())
    try:
        labels, probs = model.predict(cleaned, k=1)
    except Exception as exc:
        logger.debug("fasttext_langid: predict failed: %s", exc)
        return UNDEFINED
    if not labels or not probs:
        return UNDEFINED
    # fastText labels look like "__label__en"; strip the prefix.
    label = str(labels[0])
    code = label.replace("__label__", "")
    confidence = float(probs[0])
    if confidence < threshold:
        return LangPrediction(language=UND_LANGUAGE, confidence=confidence)
    return LangPrediction(language=code, confidence=confidence)


def predict_batch(texts: list[str]) -> list[LangPrediction]:
    """Predict languages for a batch of *texts* in one fastText call.

    fastText's ``model.predict([t1, t2, ...], k=1)`` accepts a list of
    strings and returns parallel ``(labels, probs)`` matrices in a
    single C-extension call. At 100k+ inputs this is dramatically
    faster than calling :func:`predict` per text — the per-call
    Python↔C round-trip overhead dominates the actual prediction.

    Audit bug A5 fix.

    Returns a list of :class:`LangPrediction` parallel to *texts*. The
    semantics for empty / cold-start / disabled paths match
    :func:`predict` exactly: each input gets its own
    :data:`UNDEFINED` placeholder when the dep / model / toggle is
    missing OR when its specific text is empty / below confidence.

    Cold-start safe — when no model is available, returns a list of
    :data:`UNDEFINED` of the same length as the input.
    """
    if not texts:
        return []
    cold_start = [UNDEFINED] * len(texts)
    if not HAS_FASTTEXT:
        return cold_start
    from apps.core.runtime_flags import is_enabled

    if not is_enabled("fasttext_langid.enabled", default=True):
        return cold_start
    path, threshold = _load_model_path_from_settings()
    model = _load_model(path)
    if model is None:
        return cold_start

    # fastText rejects multi-line input; collapse newlines per text.
    # Empty / whitespace-only inputs keep their UNDEFINED slot rather
    # than wasting a prediction.
    indexed_inputs: list[tuple[int, str]] = []
    for idx, raw in enumerate(texts):
        if not raw or not raw.strip():
            continue
        indexed_inputs.append((idx, " ".join(raw.split())))
    if not indexed_inputs:
        return cold_start

    cleaned_texts = [t for _, t in indexed_inputs]
    try:
        labels_matrix, probs_matrix = model.predict(cleaned_texts, k=1)
    except Exception as exc:
        logger.debug("fasttext_langid: predict_batch failed: %s", exc)
        return cold_start

    out = list(cold_start)
    for (orig_idx, _), labels, probs in zip(
        indexed_inputs, labels_matrix, probs_matrix, strict=True
    ):
        if labels is None or probs is None:
            continue
        # ``labels`` is a list of the top-1 label per input; same for probs.
        if not len(labels) or not len(probs):
            continue
        label = str(labels[0])
        code = label.replace("__label__", "")
        confidence = float(probs[0])
        if confidence < threshold:
            out[orig_idx] = LangPrediction(language=UND_LANGUAGE, confidence=confidence)
        else:
            out[orig_idx] = LangPrediction(language=code, confidence=confidence)
    return out
