"""
Plugins models — installable add-on registry and per-plugin settings.

The plugin system allows optional features (e.g. WordPress cross-linker,
Media Gallery support) to be turned on/off without breaking the core app.
"""

from django.db import models
from django.utils.text import slugify

from apps.core.models import TimestampedModel


class Plugin(TimestampedModel):
    """
    A registered add-on module that extends app functionality.

    Plugins can be enabled/disabled from the admin or Angular settings page
    without restarting Docker. The module_path is the Python import path
    to the plugin's entry point.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Human-readable plugin name, e.g. 'WordPress Cross-Linker'.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier, e.g. 'wordpress-crosslinker'. Auto-generated from name.",
    )
    description = models.TextField(
        blank=True,
        help_text="What this plugin does and what it adds to the app.",
    )
    version = models.CharField(
        max_length=20,
        default="1.0.0",
        help_text="Semantic version of this plugin.",
    )
    is_enabled = models.BooleanField(
        default=False,
        help_text="Whether this plugin is currently active. Toggle without restart.",
    )
    is_installed = models.BooleanField(
        default=False,
        help_text="Whether the plugin's files are present and loadable.",
    )
    module_path = models.CharField(
        max_length=300,
        blank=True,
        help_text="Python module import path to the plugin entry point, e.g. 'plugins.wordpress_crosslinker.plugin'.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extra plugin metadata (author, homepage, requirements, etc.).",
    )

    class Meta:
        verbose_name = "Plugin"
        verbose_name_plural = "Plugins"
        ordering = ["name"]

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.name} v{self.version} ({status})"


class PluginSetting(TimestampedModel):
    """
    A typed key-value configuration entry for a specific plugin.

    Each plugin can store its own settings here (e.g. WordPress API URL,
    Media Gallery category IDs). Displayed in the plugin settings UI.
    """

    VALUE_TYPE_CHOICES = [
        ("str", "Text"),
        ("int", "Integer"),
        ("float", "Decimal"),
        ("bool", "True / False"),
        ("json", "JSON"),
    ]

    plugin = models.ForeignKey(
        Plugin,
        on_delete=models.CASCADE,
        related_name="settings",
        help_text="The plugin this setting belongs to.",
    )
    key = models.CharField(
        max_length=100,
        help_text="Setting key, scoped to this plugin.",
    )
    value = models.TextField(
        blank=True,
        help_text="Current value of this setting.",
    )
    value_type = models.CharField(
        max_length=20,
        choices=VALUE_TYPE_CHOICES,
        default="str",
        help_text="Data type used to cast the value when reading.",
    )
    description = models.CharField(
        max_length=500,
        blank=True,
        help_text="What this setting controls.",
    )
    is_secret = models.BooleanField(
        default=False,
        help_text="If True, the value is masked in the admin UI.",
    )

    class Meta:
        verbose_name = "Plugin Setting"
        verbose_name_plural = "Plugin Settings"
        unique_together = [["plugin", "key"]]
        ordering = ["plugin", "key"]

    def __str__(self) -> str:
        return f"{self.plugin.slug}.{self.key}"
