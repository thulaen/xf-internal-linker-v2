"""Plugins app initial migration."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Plugin",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created.",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last modified.",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Human-readable plugin name.",
                        max_length=100,
                        unique=True,
                    ),
                ),
                (
                    "slug",
                    models.SlugField(
                        help_text="URL-safe identifier.", max_length=100, unique=True
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, help_text="What this plugin does."),
                ),
                (
                    "version",
                    models.CharField(
                        default="1.0.0", help_text="Semantic version.", max_length=20
                    ),
                ),
                (
                    "is_enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this plugin is currently active.",
                    ),
                ),
                (
                    "is_installed",
                    models.BooleanField(
                        default=False, help_text="Whether the plugin files are present."
                    ),
                ),
                (
                    "module_path",
                    models.CharField(
                        blank=True,
                        help_text="Python import path to the plugin entry point.",
                        max_length=300,
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True, default=dict, help_text="Extra plugin metadata."
                    ),
                ),
            ],
            options={
                "verbose_name": "Plugin",
                "verbose_name_plural": "Plugins",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="PluginSetting",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created.",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last modified.",
                    ),
                ),
                (
                    "key",
                    models.CharField(
                        help_text="Setting key, scoped to this plugin.", max_length=100
                    ),
                ),
                (
                    "value",
                    models.TextField(
                        blank=True, help_text="Current value of this setting."
                    ),
                ),
                (
                    "value_type",
                    models.CharField(
                        choices=[
                            ("str", "Text"),
                            ("int", "Integer"),
                            ("float", "Decimal"),
                            ("bool", "True / False"),
                            ("json", "JSON"),
                        ],
                        default="str",
                        help_text="Data type used to cast the value.",
                        max_length=20,
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True,
                        help_text="What this setting controls.",
                        max_length=500,
                    ),
                ),
                (
                    "is_secret",
                    models.BooleanField(
                        default=False, help_text="If True, value is masked in admin."
                    ),
                ),
                (
                    "plugin",
                    models.ForeignKey(
                        help_text="The plugin this setting belongs to.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="settings",
                        to="plugins.plugin",
                    ),
                ),
            ],
            options={
                "verbose_name": "Plugin Setting",
                "verbose_name_plural": "Plugin Settings",
                "ordering": ["plugin", "key"],
                "unique_together": {("plugin", "key")},
            },
        ),
    ]
