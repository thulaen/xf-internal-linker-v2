"""Shared lazy loader for the spaCy NLP model.

Ensures only one instance of the English model is loaded and shared across
services (sentence splitter, distiller, etc.).
"""

from __future__ import annotations

import logging
from typing import Any

_nlp = None
_spacy_available = False
_attempted = False

logger = logging.getLogger(__name__)


def get_spacy_nlp() -> Any | None:
    """Return the shared spaCy NLP model, loading it lazily if needed.

    Returns None if spaCy or the model is not available.
    """
    global _nlp, _spacy_available, _attempted

    if _attempted:
        return _nlp

    _attempted = True
    try:
        import spacy

        _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])
        _spacy_available = True
        logger.info("Successfully loaded shared spaCy model (en_core_web_sm).")
    except Exception as e:
        _nlp = None
        _spacy_available = False
        logger.warning("spaCy or en_core_web_sm not available, using fallbacks: %s", e)

    return _nlp


def is_spacy_available() -> bool:
    """Check if the shared spaCy model is successfully loaded."""
    get_spacy_nlp()
    return _spacy_available
