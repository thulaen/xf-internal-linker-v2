"""
Graph models — existing links between content items.

ExistingLink tracks links that are already live on the forum.
This data feeds the D3.js link graph visualization and is used by the
pipeline to avoid suggesting links that already exist.
"""

import uuid

from django.db import models

from apps.core.models import TimestampedModel


class ExistingLink(models.Model):
    """
    A link that already exists from one content item to another on the live forum.

    Populated during sync by parsing BBCode in post bodies.
    The pipeline checks this table to avoid suggesting duplicate links.
    Used by the D3.js link graph to show the current link topology.
    """

    EXTRACTION_METHOD_CHOICES = [
        ("bbcode_anchor", "BBCode Anchor"),
        ("html_anchor", "HTML Anchor"),
        ("bare_url", "Bare URL"),
    ]

    CONTEXT_CLASS_CHOICES = [
        ("contextual", "Contextual"),
        ("weak_context", "Weak Context"),
        ("isolated", "Isolated"),
    ]

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
    extraction_method = models.CharField(
        max_length=30,
        blank=True,
        default="",
        choices=EXTRACTION_METHOD_CHOICES,
        help_text="How this link was extracted from the source body.",
    )
    link_ordinal = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Zero-based order of this internal link within the source body.",
    )
    source_internal_link_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total resolved internal links on the source item after destination deduplication.",
    )
    context_class = models.CharField(
        max_length=30,
        blank=True,
        default="",
        choices=CONTEXT_CLASS_CHOICES,
        help_text="Whether the link appears in contextual prose, weak context, or isolated markup.",
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
            models.Index(fields=["from_content_item", "link_ordinal"]),
        ]

    def __str__(self) -> str:
        return f"{self.from_content_item} → {self.to_content_item} ('{self.anchor_text[:40]}')"


class BrokenLink(TimestampedModel):
    """A URL detected in a content item that needs link-health review."""

    STATUS_OPEN = "open"
    STATUS_IGNORED = "ignored"
    STATUS_FIXED = "fixed"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IGNORED, "Ignored"),
        (STATUS_FIXED, "Fixed"),
    ]

    broken_link_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Stable UUID used by the API and Angular frontend.",
    )
    source_content = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="broken_links",
        help_text="The content item where this URL was found.",
    )
    url = models.URLField(
        max_length=2048,
        help_text="The URL found in the source content.",
    )
    http_status = models.IntegerField(
        default=0,
        help_text="Last HTTP status code seen for this URL. 0 means connection error or timeout.",
    )
    redirect_url = models.URLField(
        max_length=2048,
        blank=True,
        default="",
        help_text="Redirect destination when the URL responds with a redirect status.",
    )
    first_detected_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this issue was first detected by the scanner.",
    )
    last_checked_at = models.DateTimeField(
        auto_now=True,
        help_text="When the scanner last checked this URL.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
        help_text="Manual review state for this broken-link record.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Reviewer notes about why the record was ignored or fixed.",
    )

    class Meta:
        verbose_name = "Broken Link"
        verbose_name_plural = "Broken Links"
        ordering = ["status", "-last_checked_at", "-first_detected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_content", "url"],
                name="graph_unique_broken_link_source_url",
            )
        ]
        indexes = [
            models.Index(fields=["status", "http_status"]),
            models.Index(fields=["source_content", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_content} -> {self.url} [{self.http_status}]"
