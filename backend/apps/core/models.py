"""
Core shared models for XF Internal Linker V2.

All app models inherit from TimestampedModel to get created_at / updated_at.
AppSetting stores typed key-value configuration for the application.
"""

from django.db import models


class TimestampedModel(models.Model):
    """
    Abstract base model that adds created_at and updated_at to every model.
    All V2 models should inherit from this.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when this record was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when this record was last modified.",
    )

    class Meta:
        abstract = True


class AppSetting(TimestampedModel):
    """
    Application-wide configuration stored in the database.
    Replaces hardcoded settings for things the user may want to change
    without restarting Docker (e.g. pipeline weights, API keys, sync schedule).
    """

    CATEGORY_CHOICES = [
        ("general", "General"),
        ("ml", "ML / AI"),
        ("link_freshness", "Link Freshness"),
        ("sync", "Sync"),
        ("performance", "Performance"),
        ("api", "API Keys"),
        ("analytics", "Analytics"),
        ("anchor", "Anchor Policy"),
        ("appearance", "Appearance"),
    ]

    VALUE_TYPE_CHOICES = [
        ("str", "Text"),
        ("int", "Integer"),
        ("float", "Decimal"),
        ("bool", "True / False"),
        ("json", "JSON"),
    ]

    key = models.CharField(
        max_length=200,
        unique=True,
        help_text="Unique setting key, e.g. 'pipeline.max_links_per_host'.",
    )
    value = models.TextField(
        help_text="Stored value (always text; cast using value_type).",
    )
    value_type = models.CharField(
        max_length=20,
        choices=VALUE_TYPE_CHOICES,
        default="str",
        help_text="Data type of the value — used to cast when reading.",
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="general",
        db_index=True,
        help_text="Grouping shown in the admin sidebar.",
    )
    description = models.CharField(
        max_length=500,
        help_text="Human-readable description of what this setting controls.",
    )
    is_secret = models.BooleanField(
        default=False,
        help_text="If True, the value is masked in the admin UI (e.g. API keys).",
    )

    class Meta:
        verbose_name = "App Setting"
        verbose_name_plural = "App Settings"
        ordering = ["category", "key"]

    def __str__(self) -> str:
        return f"{self.key} = {self.value if not self.is_secret else '••••••••'}"


class HelperNode(TimestampedModel):
    """A registered helper node for distributed workload execution (Stage 8/10).

    See docs/PERFORMANCE.md §10 for the multi-node architecture.
    """

    TIME_POLICY_CHOICES = [
        ("anytime", "Available anytime"),
        ("nighttime", "Nighttime only (21:00–06:00 UTC)"),
        ("maintenance", "Maintenance windows only"),
    ]

    name = models.CharField(max_length=100, unique=True)
    token_hash = models.CharField(
        max_length=128,
        help_text="SHA-256 hash of the registration token. Never store the raw token.",
    )
    role = models.CharField(max_length=50, default="worker")
    capabilities = models.JSONField(
        default=dict,
        help_text='{"cpu_cores": 8, "ram_gb": 16, "gpu_vram_gb": 6, "network_quality": "good"}',
    )
    allowed_queues = models.JSONField(
        default=list,
        help_text='["pipeline", "embeddings"]',
    )
    allowed_job_types = models.JSONField(
        default=list,
        help_text='["sync", "pipeline", "embeddings"]',
    )
    time_policy = models.CharField(
        max_length=20,
        choices=TIME_POLICY_CHOICES,
        default="anytime",
    )
    max_concurrency = models.IntegerField(default=2)
    cpu_cap_pct = models.IntegerField(
        default=60,
        help_text="Maximum CPU usage percentage (safety default: 60%).",
    )
    ram_cap_pct = models.IntegerField(
        default=60,
        help_text="Maximum RAM usage percentage (safety default: 60%).",
    )
    accepting_work = models.BooleanField(
        default=True,
        help_text="Operator toggle that lets the helper stay healthy but stop taking work.",
    )
    status = models.CharField(
        max_length=20,
        default="offline",
        db_index=True,
        help_text="Current state: online, busy, unhealthy, offline.",
    )
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    last_snapshot_at = models.DateTimeField(null=True, blank=True)
    active_jobs = models.IntegerField(default=0)
    queued_jobs = models.IntegerField(default=0)
    cpu_pct = models.FloatField(default=0.0)
    ram_pct = models.FloatField(default=0.0)
    gpu_util_pct = models.FloatField(null=True, blank=True)
    gpu_vram_used_mb = models.IntegerField(null=True, blank=True)
    gpu_vram_total_mb = models.IntegerField(null=True, blank=True)
    network_rtt_ms = models.IntegerField(null=True, blank=True)
    native_kernels_healthy = models.BooleanField(default=False)
    warmed_model_keys = models.JSONField(
        default=list,
        help_text='["embedding:BAAI/bge-m3:fr020-v1"]',
    )

    class Meta:
        verbose_name = "Helper Node"
        verbose_name_plural = "Helper Nodes"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"


class QuarantineRecord(TimestampedModel):
    """First-class quarantine record (plan item 16).

    Replaces the bare boolean ``PipelineRun.is_quarantined``.  A QuarantineRecord
    stores *why* an item was quarantined, *what* is affected, *which* safe fix
    exists for it (matched against the frontend runbook library), and whether
    it can resume from a checkpoint.  The `PipelineRun.is_quarantined` flag is
    kept for backwards compatibility but is now a mirror of
    ``active QuarantineRecord exists``; new code should read/write via this
    model exclusively.

    Storage estimate: ~500 KB at 30 days with an autoprune at 90 days
    (tracked under plan item 19 retention work).
    """

    REASON_REPEATED_FAILURE = "repeated_failure"
    REASON_BAD_CREDENTIALS = "bad_credentials"
    REASON_MALFORMED_IMPORT = "malformed_import"
    REASON_STALLED_CRAWL = "stalled_crawl"
    REASON_BROKEN_WARMUP = "broken_warmup"
    REASON_DUPLICATE_CONFLICT = "duplicate_conflict"
    REASON_OTHER = "other"

    REASON_CHOICES = [
        (REASON_REPEATED_FAILURE, "Repeated failures"),
        (REASON_BAD_CREDENTIALS, "Bad credentials"),
        (REASON_MALFORMED_IMPORT, "Malformed import"),
        (REASON_STALLED_CRAWL, "Stalled crawl"),
        (REASON_BROKEN_WARMUP, "Broken warmup"),
        (REASON_DUPLICATE_CONFLICT, "Duplicate conflicting job"),
        (REASON_OTHER, "Other"),
    ]

    # What's quarantined.  Polymorphic pointer: most records point at a
    # PipelineRun today, but the same table can carry sync jobs, suggestions,
    # or crawl sessions tomorrow without a schema change.
    related_object_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="e.g. 'pipeline_run', 'sync_job', 'suggestion', 'crawl_session'.",
    )
    related_object_id = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Primary key or UUID of the quarantined object as a string.",
    )

    # Why it was quarantined.
    reason = models.CharField(
        max_length=48,
        choices=REASON_CHOICES,
        default=REASON_REPEATED_FAILURE,
        db_index=True,
    )
    reason_detail = models.TextField(
        blank=True,
        help_text="Plain-English extended explanation shown to the user.",
    )

    # Everything else affected by this quarantine (list of ids, paths, or refs).
    affected_items = models.JSONField(
        default=list,
        blank=True,
        help_text='["content_item:123", "sync_job:abc"] — items impacted beyond the primary.',
    )

    # Which runbook from the frontend library can fix this.
    fix_available = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        help_text="Runbook id, e.g. 'reset-quarantined-job' or 'restart-stuck-pipeline'.",
    )

    # Checkpoint resumability.
    resume_from_checkpoint = models.BooleanField(default=False)
    checkpoint_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="Opaque checkpoint handle the worker can pick up at resume.",
    )

    # Lifecycle.
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolved_by = models.CharField(
        max_length=64,
        blank=True,
        help_text="'user', 'auto', or 'runbook:<id>' — who/what closed this.",
    )
    resolved_note = models.TextField(blank=True)

    class Meta:
        verbose_name = "Quarantine Record"
        verbose_name_plural = "Quarantine Records"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["related_object_type", "related_object_id"],
                name="qrec_related_idx",
            ),
            models.Index(fields=["resolved_at"], name="qrec_resolved_idx"),
        ]

    # Convenience -----------------------------------------------------

    @property
    def is_open(self) -> bool:
        """True while the quarantine has not been resolved."""
        return self.resolved_at is None

    def __str__(self) -> str:
        state = "open" if self.is_open else "resolved"
        return f"QuarantineRecord<{self.related_object_type}:{self.related_object_id} {self.reason} {state}>"


# Phase OB / Gaps 131 + 132 — Feature flags + A/B variants + exposures.
# Defined in ``feature_flags.py`` to keep this file manageable; re-exported
# so Django's app registry picks them up at makemigrations time.
from .feature_flags import FeatureFlag, FeatureFlagExposure  # noqa: E402, F401
from .runtime_models import (  # noqa: E402, F401
    HardwareCapabilitySnapshot,
    RuntimeAuditLog,
    RuntimeModelBackfillPlan,
    RuntimeModelPlacement,
    RuntimeModelRegistry,
)
