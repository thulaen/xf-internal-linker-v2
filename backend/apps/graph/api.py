"""Public API for the graph module.

This module defines the public interface for the graph module, allowing other
modules (like pipeline and suggestions) to read graph signals without coupling
to internal models or logic.
"""

from typing import Optional

from apps.content.models import ContentItem
from apps.graph.models import GraphSignalRun, LinkPredictionCandidate, NodeGraphSignal


def get_current_run() -> Optional[GraphSignalRun]:
    """Return the currently active GraphSignalRun, or None if none exists."""
    return GraphSignalRun.objects.filter(status=GraphSignalRun.STATUS_CURRENT).first()


def latest_node_signal(item: ContentItem) -> Optional[NodeGraphSignal]:
    """Return the NodeGraphSignal for the given item from the current run."""
    run = get_current_run()
    if not run:
        return None
    return NodeGraphSignal.objects.filter(run=run, content_item=item).first()


def link_prediction_candidates(item: ContentItem, as_destination: bool = False) -> list[LinkPredictionCandidate]:
    """Return LinkPredictionCandidate rows for the given item from the current run.
    If as_destination is True, finds candidates where to_item=item.
    Otherwise, finds candidates where from_item=item.
    """
    run = get_current_run()
    if not run:
        return []
    if as_destination:
        return list(LinkPredictionCandidate.objects.filter(run=run, to_item=item).select_related("from_item"))
    return list(LinkPredictionCandidate.objects.filter(run=run, from_item=item).select_related("to_item"))
