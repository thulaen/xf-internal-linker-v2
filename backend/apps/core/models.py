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
