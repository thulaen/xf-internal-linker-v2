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
    status = models.CharField(
        max_length=20,
        default="offline",
        db_index=True,
        help_text="Current state: online, busy, unhealthy, offline.",
    )
    last_heartbeat = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Helper Node"
        verbose_name_plural = "Helper Nodes"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"
