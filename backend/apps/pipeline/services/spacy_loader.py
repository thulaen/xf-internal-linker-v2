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


def _emit_spacy_event(event_type: str, title: str, message: str, severity: str) -> None:
    try:
        from apps.ops_feed.services import emit

        emit(
            event_type=event_type,
            plain_english=f"{title}: {message}",
            source="nlp",
            severity=severity,
            related_entity_type="component",
            related_entity_id="spacy_loader",
            runtime_context={"component": "spacy_loader"},
        )
    except Exception:  # noqa: BLE001
        logger.debug("spacy_loader: operations-feed emit failed", exc_info=True)


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

        _nlp = spacy.load("en_core_web_sm")
        _spacy_available = True
        logger.info("Successfully loaded shared spaCy model (en_core_web_sm).")
        _emit_spacy_event(
            "nlp.spacy_ready",
            "spaCy NLP model loaded",
            "The shared English NLP model is ready for sentence splitting and text enrichment.",
            "success",
        )
    except Exception as e:
        _nlp = None
        _spacy_available = False
        logger.warning("spaCy or en_core_web_sm not available, using fallbacks: %s", e)
        _emit_spacy_event(
            "nlp.spacy_fallback",
            "spaCy NLP fallback active",
            "The English NLP model is not available, so the pipeline is using simpler fallback text handling.",
            "warning",
        )

    return _nlp


def is_spacy_available() -> bool:
    """Check if the shared spaCy model is successfully loaded."""
    get_spacy_nlp()
    return _spacy_available
