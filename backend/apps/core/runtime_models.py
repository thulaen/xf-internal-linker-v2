"""Runtime registry and hardware snapshot models.

These models extend the existing runtime/pause/helper ownership lines instead
of creating a second control plane.
"""

from django.db import models

from .models import TimestampedModel


class RuntimeModelRegistry(TimestampedModel):
    """Registered runtime model definition owned by FR-020."""

    TASK_TYPE_CHOICES = [
        ("embedding", "Embedding"),
        ("spacy", "spaCy"),
        ("helper", "Helper"),
    ]
    ROLE_CHOICES = [
        ("champion", "Champion"),
        ("candidate", "Candidate"),
        ("retired", "Retired"),
    ]
    STATUS_CHOICES = [
        ("registered", "Registered"),
        ("downloading", "Downloading"),
        ("warming", "Warming"),
        ("ready", "Ready"),
        ("draining", "Draining"),
        ("failed", "Failed"),
        ("deleted", "Deleted"),
    ]

    task_type = models.CharField(
        max_length=32,
        choices=TASK_TYPE_CHOICES,
        default="embedding",
        db_index=True,
    )
    model_name = models.CharField(max_length=255, db_index=True)
    model_family = models.CharField(max_length=100, blank=True)
    dimension = models.IntegerField(null=True, blank=True)
    device_target = models.CharField(max_length=32, default="cpu")
    batch_size = models.IntegerField(default=32)
    memory_profile = models.JSONField(default=dict, blank=True)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="candidate",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="registered",
        db_index=True,
    )
    health_result = models.JSONField(default=dict, blank=True)
    algorithm_version = models.CharField(max_length=64, default="fr020-v1")
    promoted_at = models.DateTimeField(null=True, blank=True)
    draining_since = models.DateTimeField(null=True, blank=True)
    last_warmup_result = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Runtime Model Registry"
        verbose_name_plural = "Runtime Model Registry"
        ordering = ["task_type", "-promoted_at", "model_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["task_type", "model_name", "algorithm_version"],
                name="runtime_model_unique_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.task_type}:{self.model_name} [{self.role}/{self.status}]"


class RuntimeModelPlacement(TimestampedModel):
    """Executor-specific placement of a registered runtime model."""

    EXECUTOR_TYPE_CHOICES = [
        ("primary", "Primary"),
        ("helper", "Helper"),
    ]
    STATUS_CHOICES = [
        ("registered", "Registered"),
        ("downloading", "Downloading"),
        ("warming", "Warming"),
        ("ready", "Ready"),
        ("draining", "Draining"),
        ("failed", "Failed"),
        ("deleted", "Deleted"),
    ]

    registry = models.ForeignKey(
        RuntimeModelRegistry,
        on_delete=models.CASCADE,
        related_name="placements",
    )
    executor_type = models.CharField(
        max_length=20,
        choices=EXECUTOR_TYPE_CHOICES,
        default="primary",
        db_index=True,
    )
    helper = models.ForeignKey(
        "core.HelperNode",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="model_placements",
    )
    artifact_path = models.CharField(max_length=500, blank=True)
    artifact_checksum = models.CharField(max_length=128, blank=True)
    disk_bytes = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="registered",
        db_index=True,
    )
    last_used_at = models.DateTimeField(null=True, blank=True)
    warmed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Runtime Model Placement"
        verbose_name_plural = "Runtime Model Placements"
        ordering = ["registry__task_type", "executor_type", "helper__name"]

    def __str__(self) -> str:
        owner = "primary" if self.executor_type == "primary" else self.helper_id
        return f"{self.registry.model_name} on {owner} [{self.status}]"


class RuntimeModelBackfillPlan(TimestampedModel):
    """Tracks an embedding backfill required by a model swap."""

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    from_model = models.ForeignKey(
        RuntimeModelRegistry,
        on_delete=models.CASCADE,
        related_name="backfills_from",
    )
    to_model = models.ForeignKey(
        RuntimeModelRegistry,
        on_delete=models.CASCADE,
        related_name="backfills_to",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="queued",
        db_index=True,
    )
    compatibility_status = models.CharField(max_length=32, default="compatible")
    progress_pct = models.FloatField(default=0.0)
    checkpoint = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Runtime Model Backfill Plan"
        verbose_name_plural = "Runtime Model Backfill Plans"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Backfill {self.from_model_id}->{self.to_model_id} [{self.status}]"


class HardwareCapabilitySnapshot(TimestampedModel):
    """Latest hardware capability snapshot for the primary node or a helper."""

    NODE_KIND_CHOICES = [
        ("primary", "Primary"),
        ("helper", "Helper"),
    ]

    node_kind = models.CharField(
        max_length=20,
        choices=NODE_KIND_CHOICES,
        default="primary",
        db_index=True,
    )
    helper = models.ForeignKey(
        "core.HelperNode",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="hardware_snapshots",
    )
    cpu_cores = models.IntegerField(default=0)
    ram_gb = models.FloatField(default=0.0)
    gpu_name = models.CharField(max_length=200, blank=True)
    gpu_vram_gb = models.FloatField(default=0.0)
    disk_free_gb = models.FloatField(default=0.0)
    native_kernels_healthy = models.BooleanField(default=False)
    snapshot = models.JSONField(default=dict, blank=True)
    detected_upgrade = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Hardware Capability Snapshot"
        verbose_name_plural = "Hardware Capability Snapshots"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.node_kind} snapshot @ {self.created_at:%Y-%m-%d %H:%M:%S}"


class RuntimeAuditLog(TimestampedModel):
    """Human-readable runtime audit trail."""

    action = models.CharField(max_length=64, db_index=True)
    subject_type = models.CharField(max_length=64, db_index=True)
    subject_id = models.CharField(max_length=128, blank=True)
    actor = models.CharField(max_length=64, blank=True)
    message = models.CharField(max_length=500)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Runtime Audit Log"
        verbose_name_plural = "Runtime Audit Logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action}: {self.message}"
