"""
Phase OF — OperationEvent table.

Stores the ambient feed the UI streams. Rows are cheap — severity=info
events vastly outnumber errors — so the table has a conservative
retention policy (3 days kept, older pruned nightly via a future task).

Dedup: `(event_type, source, related_entity_type, related_entity_id)`
within a 60-second window rolls up into a single row via `occurrence_count`.
"""

from __future__ import annotations

from django.db import models


class OperationEvent(models.Model):
    """A single ambient event rendered in the Operations Feed."""

    SEVERITY_INFO = "info"
    SEVERITY_WARNING = "warning"
    SEVERITY_ERROR = "error"
    SEVERITY_SUCCESS = "success"
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, "Info"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_ERROR, "Error"),
        (SEVERITY_SUCCESS, "Success"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    event_type = models.CharField(max_length=60, db_index=True)
    source = models.CharField(
        max_length=60,
        db_index=True,
        help_text="Which subsystem emitted this (e.g. 'pipeline', 'crawler').",
    )
    plain_english = models.TextField(
        help_text="Operator-facing sentence the UI renders verbatim."
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_INFO,
        db_index=True,
    )
    related_entity_type = models.CharField(max_length=60, blank=True, db_index=True)
    related_entity_id = models.CharField(max_length=100, blank=True, db_index=True)
    runtime_context = models.JSONField(default=dict, blank=True)
    # Stable hash the dedup engine uses to roll up repeats within a 60s
    # window. Computed in the emitter, stored so the UI can collapse
    # bursts retroactively.
    dedup_key = models.CharField(max_length=100, blank=True, db_index=True)
    occurrence_count = models.IntegerField(default=1)
    # Optional linkage to an ErrorLog row — the UI shows a "Fix"
    # shortcut when present.
    error_log_id = models.IntegerField(null=True, blank=True, db_index=True)

    class Meta:
        app_label = "ops_feed"
        verbose_name = "Operation Event"
        verbose_name_plural = "Operation Events"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["severity", "-timestamp"], name="ofeed_sev_ts_idx"),
            models.Index(fields=["dedup_key", "-timestamp"], name="ofeed_dedup_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover — admin cosmetic
        return f"[{self.severity}] {self.event_type}: {self.plain_english[:60]}"
