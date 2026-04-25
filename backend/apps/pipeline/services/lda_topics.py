"""LDA topic model — pick #18.

Reference
---------
Blei, D. M., Ng, A. Y., & Jordan, M. I. (2003). "Latent Dirichlet
Allocation." *Journal of Machine Learning Research*, 3, 993-1022.

LDA learns a soft topic distribution per document — i.e. each
document is a mixture of K latent topics, and each topic is a
distribution over the vocabulary. Useful for downstream features:
"how topically aligned is this candidate destination with this host
sentence?"

Wraps ``gensim.models.LdaModel``. The training side is invoked by
the W1 ``lda_topic_refresh`` scheduled job; this module exposes the
inference side (load a trained model, score a document → topic
distribution) plus thin training helpers for the W1 job.

Cold-start safe at every layer:
- Missing pip dep → ``HAS_GENSIM = False``; all functions return
  empty / ``None``.
- Model file not on disk → :func:`load_model` returns ``None``.
- :func:`infer_topics` with no model → returns an empty distribution.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

try:
    from gensim.corpora import Dictionary as _Dictionary
    from gensim.models import LdaModel as _LdaModel

    HAS_GENSIM = True
except ImportError:  # pragma: no cover — depends on pip env
    _Dictionary = None  # type: ignore[assignment]
    _LdaModel = None  # type: ignore[assignment]
    HAS_GENSIM = False


logger = logging.getLogger(__name__)


KEY_MODEL_PATH = "lda.model_path"
KEY_DICT_PATH = "lda.dictionary_path"
KEY_NUM_TOPICS = "lda.num_topics"
DEFAULT_NUM_TOPICS: int = 50


@dataclass(frozen=True)
class TopicDistribution:
    """One document's soft topic mixture.

    ``weights`` is a list of (topic_id, probability) pairs sorted by
    descending probability. Empty when no model is loaded.
    """

    weights: list[tuple[int, float]]

    @property
    def is_empty(self) -> bool:
        return not self.weights


EMPTY_DISTRIBUTION = TopicDistribution(weights=[])


_MODEL_CACHE: tuple[str, object, object] | None = None  # (path, lda, dictionary)


def is_available() -> bool:
    """True when ``gensim`` is importable."""
    return HAS_GENSIM


def _read_paths_from_settings() -> tuple[str, str]:
    try:
        from apps.core.models import AppSetting

        rows = dict(
            AppSetting.objects.filter(
                key__in=[KEY_MODEL_PATH, KEY_DICT_PATH]
            ).values_list("key", "value")
        )
    except Exception:
        return "", ""
    return rows.get(KEY_MODEL_PATH, "") or "", rows.get(KEY_DICT_PATH, "") or ""


def load_model() -> tuple[object, object] | None:
    """Return the cached ``(LdaModel, Dictionary)`` or load from disk.

    Returns ``None`` when:
    - Gensim isn't installed.
    - The path AppSettings are empty (no producer has trained yet).
    - The files don't exist on disk.
    """
    global _MODEL_CACHE
    if not HAS_GENSIM:
        return None
    model_path, dict_path = _read_paths_from_settings()
    if not model_path or not dict_path:
        return None
    if not os.path.exists(model_path) or not os.path.exists(dict_path):
        return None
    if _MODEL_CACHE is not None and _MODEL_CACHE[0] == model_path:
        return (_MODEL_CACHE[1], _MODEL_CACHE[2])
    try:
        lda = _LdaModel.load(model_path)
        dictionary = _Dictionary.load(dict_path)
    except Exception as exc:
        logger.warning("lda_topics: load failed: %s", exc)
        return None
    _MODEL_CACHE = (model_path, lda, dictionary)
    return lda, dictionary


def infer_topics(tokens: list[str]) -> TopicDistribution:
    """Return the topic mixture for *tokens* (a list of words).

    Cold-start safe at every layer; returns
    :data:`EMPTY_DISTRIBUTION` when no model is available or when
    the operator has flipped the ``lda.enabled`` toggle off.
    """
    if not tokens:
        return EMPTY_DISTRIBUTION
    from apps.core.runtime_flags import is_enabled

    if not is_enabled("lda.enabled", default=True):
        return EMPTY_DISTRIBUTION
    loaded = load_model()
    if loaded is None:
        return EMPTY_DISTRIBUTION
    lda, dictionary = loaded
    bow = dictionary.doc2bow(tokens)
    raw = lda.get_document_topics(bow)
    sorted_pairs = sorted(
        ((int(t), float(p)) for t, p in raw),
        key=lambda item: -item[1],
    )
    return TopicDistribution(weights=sorted_pairs)


def fit_and_save(
    documents: list[list[str]],
    *,
    model_path: str,
    dict_path: str,
    num_topics: int = DEFAULT_NUM_TOPICS,
    passes: int = 5,
) -> bool:
    """Train an LDA model from *documents* and save to disk.

    Each ``documents[i]`` is a list of pre-tokenised words for one
    doc. Returns ``True`` when training + persistence succeed,
    ``False`` when gensim is missing / training fails / fewer than
    2 documents are provided.

    Wired into the W1 ``lda_topic_refresh`` job; not called from the
    inference path.
    """
    if not HAS_GENSIM:
        logger.info("lda_topics.fit_and_save: gensim not installed — skip")
        return False
    if len(documents) < 2:
        logger.info(
            "lda_topics.fit_and_save: %d documents (< 2) — skip", len(documents)
        )
        return False
    try:
        dictionary = _Dictionary(documents)
        corpus = [dictionary.doc2bow(doc) for doc in documents]
        lda = _LdaModel(
            corpus=corpus,
            id2word=dictionary,
            num_topics=num_topics,
            passes=passes,
        )
        os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(dict_path) or ".", exist_ok=True)
        lda.save(model_path)
        dictionary.save(dict_path)
    except Exception as exc:
        logger.warning("lda_topics.fit_and_save failed: %s", exc)
        return False
    # Reset the cache so subsequent infer_topics calls pick up the
    # new model.
    global _MODEL_CACHE
    _MODEL_CACHE = None
    return True
