"""
Pipeline models — full field definitions added in Phase 1.
Stage 10: JobLease model for ownership tracking.
"""

from django.db import models

from apps.core.models import TimestampedModel  # noqa: F401


class JobLease(TimestampedModel):
    """Ownership lease for active tasks.

    Prevents dual control — only one worker can own a task at a time.
    Expired heartbeats → status='resumable', safe for reassignment.

    See docs/PERFORMANCE.md §10 for the multi-node architecture.
    """

    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("expired", "Expired"),
        ("resumable", "Resumable"),
    ]

    task_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Celery task ID or unique job identifier.",
    )
    task_type = models.CharField(
        max_length=50,
        help_text="Type of task: sync, pipeline, embeddings, broken_link_scan, etc.",
    )
    owner = models.CharField(
        max_length=200,
        help_text="Worker name or helper node name that owns this task.",
    )
    acquired_at = models.DateTimeField(
        help_text="When this lease was acquired.",
    )
    last_heartbeat = models.DateTimeField(
        help_text="Last time the owner confirmed it is still working on this task.",
    )
    expires_at = models.DateTimeField(
        db_index=True,
        help_text="If no heartbeat arrives by this time, the lease is considered expired.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        db_index=True,
    )

    class Meta:
        verbose_name = "Job Lease"
        verbose_name_plural = "Job Leases"
        ordering = ["-acquired_at"]

    def __str__(self) -> str:
        return f"Lease {self.task_id[:12]} → {self.owner} ({self.status})"


# ---------------------------------------------------------------------------
# Embedding provider infrastructure (plan Parts 1, 4, 9)
# ---------------------------------------------------------------------------


class EmbeddingCostLedger(TimestampedModel):
    """Per-job, per-provider token + cost accounting (plan Part 1).

    One row per ``(job_id, provider)`` via the unique constraint — on resume
    with the same provider, subsequent batches update the row (via
    ``update_or_create``) rather than inserting duplicates. Resuming with a
    different provider writes a new row. Monthly budget gate sums this table.

    Disk footprint: ~200 bytes per row. For typical usage (monthly cycle × 3
    providers × 100 jobs) this table stays well under 1 MB.
    """

    job_id = models.CharField(max_length=64, db_index=True)
    provider = models.CharField(max_length=32, db_index=True)
    signature = models.CharField(max_length=64)
    items = models.IntegerField(default=0)
    tokens_input = models.BigIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)

    class Meta:
        verbose_name = "Embedding Cost Ledger"
        verbose_name_plural = "Embedding Cost Ledgers"
        unique_together = [["job_id", "provider"]]
        indexes = [
            models.Index(fields=["provider", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider} job={self.job_id[:12]} ${self.cost_usd}"


class EmbeddingBakeoffResult(TimestampedModel):
    """Per-run MRR/NDCG/Recall for each provider (plan Part 4, FR-232).

    Streaming eval writes one row per ``(job_id, provider)``. Unique constraint
    guarantees no duplicates even if the task crashes mid-run and resumes.

    Disk footprint: ~500 bytes per row. Tiny.
    """

    job_id = models.CharField(max_length=64, db_index=True)
    provider = models.CharField(max_length=32)
    signature = models.CharField(max_length=64)
    sample_size = models.IntegerField(default=0)
    mrr_at_10 = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    ndcg_at_10 = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    recall_at_10 = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    mean_positive_cosine = models.DecimalField(
        max_digits=6, decimal_places=4, default=0
    )
    mean_negative_cosine = models.DecimalField(
        max_digits=6, decimal_places=4, default=0
    )
    separation_score = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms_p50 = models.IntegerField(default=0)
    latency_ms_p95 = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Embedding Bake-off Result"
        verbose_name_plural = "Embedding Bake-off Results"
        unique_together = [["job_id", "provider"]]
        indexes = [
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"bakeoff {self.provider} ndcg={self.ndcg_at_10} ({self.job_id[:8]})"


class EmbeddingGateDecision(TimestampedModel):
    """Quality-gate decision log (plan Part 9, FR-236).

    Written by ``embedding_quality_gate.QualityGate.evaluate`` before each
    replacement attempt. One row per evaluated item. Enables audit and
    diagnostics (why did the gate reject this?) without keeping the vectors
    themselves — just the decision metadata.

    Disk footprint target ≤128 MB total across all history. ``action`` +
    ``reason`` are short strings; no vector fields.
    """

    ACTION_REPLACE = "REPLACE"
    ACTION_REJECT = "REJECT"
    ACTION_NOOP = "NOOP"
    ACTION_ACCEPT_NEW = "ACCEPT_NEW"

    ACTION_CHOICES = [
        (ACTION_REPLACE, "Replace"),
        (ACTION_REJECT, "Reject"),
        (ACTION_NOOP, "No-op"),
        (ACTION_ACCEPT_NEW, "Accept new"),
    ]

    item_id = models.IntegerField(db_index=True)
    item_kind = models.CharField(max_length=16)  # "content_item" | "sentence"
    old_signature = models.CharField(max_length=64, blank=True)
    new_signature = models.CharField(max_length=64)
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True)
    reason = models.CharField(max_length=64)
    score_delta = models.DecimalField(max_digits=8, decimal_places=6, default=0)

    class Meta:
        verbose_name = "Embedding Gate Decision"
        verbose_name_plural = "Embedding Gate Decisions"
        indexes = [
            models.Index(fields=["-created_at", "action"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.item_kind}={self.item_id} ({self.reason})"
