"""
Graduated penalty signal for the value model.

Computes a composite 0.0-1.0 penalty from three sub-signals:
  density  — how close the host page is to its existing-link limit
  anchor   — how far the anchor text overshoots the max-words limit
  cluster  — how many approved suggestions sit nearby in the same paragraph
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


def _sigmoid(x: float, k: float, threshold: float) -> float:
    """Logistic sigmoid centred on *threshold*.

    Returns ~0 when x << threshold and ~1 when x >> threshold.
    *k* controls steepness.
    """
    return 1.0 / (1.0 + math.exp(-k * (x - threshold)))


def _get_setting_int(key: str, default: int) -> int:
    """Read a single AppSetting integer, returning *default* on any failure."""
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=key).first()
        if row is not None:
            return int(row.value)
    except Exception:
        logger.debug("AppSetting %s not available; using default %d", key, default)
    return default


def _density_penalty(host_content_id: int, max_links: int) -> float:
    """Sigmoid on existing_outgoing_links / max_links.

    k=3.0, threshold=0.7 — starts penalizing at 70 % of the cap.
    """
    if max_links <= 0:
        return 0.0

    try:
        from apps.graph.models import ExistingLink

        count = ExistingLink.objects.filter(
            from_content_item_id=host_content_id,
        ).count()
    except Exception:
        return 0.0

    ratio = count / max_links
    return _sigmoid(ratio, k=3.0, threshold=0.7)


def _anchor_penalty(anchor_text: str | None, max_words: int) -> float:
    """Linear overshoot beyond *max_words*.

    Returns 0 when word count <= max_words, scales linearly up to 1.0.
    """
    if not anchor_text or max_words <= 0:
        return 0.0

    word_count = len(anchor_text.split())
    return min(1.0, max(0.0, word_count / max_words - 1.0))


def _cluster_penalty(
    host_content_id: int,
    sentence_position: int | None,
    paragraph_window: int,
) -> float:
    """Sigmoid on nearby approved/applied suggestions within the paragraph window.

    k=2.0, threshold=1.0 — starts penalizing when there is already one
    approved neighbour within ±paragraph_window sentence positions.
    """
    if sentence_position is None or paragraph_window <= 0:
        return 0.0

    try:
        from apps.suggestions.models import Suggestion

        nearby = Suggestion.objects.filter(
            host_id=host_content_id,
            status__in=("approved", "applied", "verified"),
            host_sentence__position__gte=sentence_position - paragraph_window,
            host_sentence__position__lte=sentence_position + paragraph_window,
        ).count()
    except Exception:
        return 0.0

    return _sigmoid(nearby, k=2.0, threshold=1.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_penalty_signal(
    host_content_id: int,
    anchor_text: str | None,
    sentence_position: int | None,
) -> float:
    """Compute graduated penalty signal (0.0 = no penalty, 1.0 = max penalty).

    Three sub-signals:
      1. density_penalty  — sigmoid on existing_links / max_existing_links_per_host
         k=3.0, threshold=0.7 (start penalizing at 70 % of limit)
      2. anchor_penalty   — linear overshoot beyond max_anchor_words
         min(1.0, max(0, word_count / max_words - 1.0))
      3. cluster_penalty  — sigmoid on nearby_approved_suggestions / paragraph_window
         k=2.0, threshold=1.0

    Composite: 0.35 * density + 0.35 * anchor + 0.30 * cluster
    """
    max_links = _get_setting_int("spam_guards.max_existing_links_per_host", 3)
    max_words = _get_setting_int("spam_guards.max_anchor_words", 4)
    window = _get_setting_int("spam_guards.paragraph_window", 3)

    density = _density_penalty(host_content_id, max_links)
    anchor = _anchor_penalty(anchor_text, max_words)
    cluster = _cluster_penalty(host_content_id, sentence_position, window)

    return 0.35 * density + 0.35 * anchor + 0.30 * cluster
