"""
Plugin hook interface — abstract base class that plugins implement.

Plugins register by subclassing PluginHooks and implementing whichever
hooks they need. Unimplemented hooks are no-ops.
"""

from __future__ import annotations

from typing import Any


class PluginHooks:
    """Base class for plugin hook implementations.

    Subclass this and override the hooks you want to respond to.
    All hooks receive keyword arguments for forward compatibility.
    """

    def pre_pipeline(self, *, scope_ids: list[int], mode: str, **kwargs: Any) -> None:
        """Called before a pipeline run starts."""

    def post_ranking(self, *, suggestions: list[Any], **kwargs: Any) -> list[Any]:
        """Called after scoring, before suggestion creation. Return modified suggestions."""
        return suggestions

    def on_suggestion_approve(self, *, suggestion_id: str, **kwargs: Any) -> None:
        """Called when a reviewer approves a suggestion."""

    def on_content_import(
        self, *, content_item_ids: list[int], source: str, **kwargs: Any
    ) -> None:
        """Called after content is imported (post-ingest stage)."""
