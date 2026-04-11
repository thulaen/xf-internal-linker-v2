"""FR-025 — Session Co-Occurrence & Behavioral Hub models."""

from __future__ import annotations

import uuid

from django.db import models


class SessionCoOccurrencePair(models.Model):
    """Pairwise co-occurrence count for two content items observed in the same GA4 session."""

    source_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="cooccurrence_as_source",
        db_index=True,
    )
    dest_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="cooccurrence_as_dest",
        db_index=True,
    )
    co_session_count = models.IntegerField(
        help_text="Number of sessions in which both articles were viewed.",
    )
    source_session_count = models.IntegerField(
        help_text="Number of sessions in which the source article was viewed.",
    )
    dest_session_count = models.IntegerField(
        help_text="Number of sessions in which the destination article was viewed.",
    )
    jaccard_similarity = models.FloatField(
        db_index=True,
        help_text="co_session_count / (source + dest - co). Bounded [0, 1].",
    )
    lift = models.FloatField(
        help_text="P(A∩B) / (P(A) × P(B)). Values > 1 mean articles are co-read more than chance.",
    )
    log_likelihood_score = models.FloatField(
        default=0.0,
        db_index=True,
        help_text=(
            "Dunning 1993 log-likelihood ratio (G-squared) for this pair. "
            "Higher = more statistically surprising co-occurrence."
        ),
    )
    last_computed_at = models.DateTimeField(auto_now=True)
    data_window_start = models.DateField()
    data_window_end = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_content_item", "dest_content_item"],
                name="unique_cooccurrence_pair",
            )
        ]
        indexes = [
            models.Index(fields=["source_content_item", "jaccard_similarity"]),
            models.Index(fields=["dest_content_item", "jaccard_similarity"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.source_content_item_id} → {self.dest_content_item_id} "
            f"(jaccard={self.jaccard_similarity:.3f})"
        )


class SessionCoOccurrenceRun(models.Model):
    """Metadata for each co-occurrence computation run."""

    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    run_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING
    )
    data_window_start = models.DateField()
    data_window_end = models.DateField()
    sessions_processed = models.IntegerField(default=0)
    pairs_written = models.IntegerField(default=0)
    ga4_rows_fetched = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"CoOccurrenceRun {self.run_id} [{self.status}]"


class BehavioralHub(models.Model):
    """A cluster of articles that users frequently navigate between in the same session."""

    METHOD_THRESHOLD = "threshold_connected_components"
    METHOD_MANUAL = "manual"
    METHOD_CHOICES = [
        (METHOD_THRESHOLD, "Threshold Connected Components"),
        (METHOD_MANUAL, "Manual"),
    ]

    hub_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    detection_method = models.CharField(
        max_length=40,
        choices=METHOD_CHOICES,
        default=METHOD_THRESHOLD,
    )
    min_jaccard_used = models.FloatField(
        help_text="Minimum Jaccard threshold used when this hub was detected.",
    )
    member_count = models.IntegerField(default=0)
    auto_link_enabled = models.BooleanField(
        default=False,
        help_text="When true, hub-pair suggestions are flagged with candidate_origin=behavioral_hub.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-member_count", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.member_count} members)"


class BehavioralHubMembership(models.Model):
    """Membership of a ContentItem in a BehavioralHub."""

    SOURCE_AUTO = "auto_detected"
    SOURCE_MANUAL_ADD = "manual_add"
    SOURCE_MANUAL_REMOVE = "manual_remove_override"
    SOURCE_CHOICES = [
        (SOURCE_AUTO, "Auto Detected"),
        (SOURCE_MANUAL_ADD, "Manually Added"),
        (SOURCE_MANUAL_REMOVE, "Manually Removed (Override)"),
    ]

    hub = models.ForeignKey(
        BehavioralHub,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="behavioral_hub_memberships",
    )
    membership_source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        default=SOURCE_AUTO,
    )
    co_occurrence_strength = models.FloatField(
        default=0.0,
        help_text="Average Jaccard similarity to other hub members.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hub", "content_item"],
                name="unique_hub_membership",
            )
        ]

    def __str__(self) -> str:
        return f"{self.hub.name} ← {self.content_item_id} ({self.membership_source})"
