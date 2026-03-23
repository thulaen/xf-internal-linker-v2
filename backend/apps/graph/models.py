"""
Graph models — existing links between content items.

ExistingLink tracks links that are already live on the forum.
This data feeds the D3.js link graph visualization and is used by the
pipeline to avoid suggesting links that already exist.
"""

from django.db import models


class ExistingLink(models.Model):
    """
    A link that already exists from one content item to another on the live forum.

    Populated during sync by parsing BBCode in post bodies.
    The pipeline checks this table to avoid suggesting duplicate links.
    Used by the D3.js link graph to show the current link topology.
    """

    from_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="outgoing_links",
        help_text="The content item that contains this link (the host).",
    )
    to_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="incoming_links",
        help_text="The content item being linked to (the destination).",
    )
    anchor_text = models.CharField(
        max_length=500,
        blank=True,
        help_text="The anchor text used for this link on the live forum.",
    )
    discovered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this link was first detected during a sync.",
    )

    class Meta:
        verbose_name = "Existing Link"
        verbose_name_plural = "Existing Links"
        unique_together = [["from_content_item", "to_content_item", "anchor_text"]]
        indexes = [
            models.Index(fields=["to_content_item"]),
            models.Index(fields=["from_content_item"]),
        ]

    def __str__(self) -> str:
        return f"{self.from_content_item} → {self.to_content_item} ('{self.anchor_text[:40]}')"
