"""
Plugins admin — Plugin registry and PluginSetting.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Plugin, PluginSetting


class PluginSettingInline(TabularInline):
    """Inline settings inside a Plugin."""

    model = PluginSetting
    fields = ["key", "value", "value_type", "is_secret", "description"]
    readonly_fields = ["key", "value_type", "description"]
    extra = 0


@admin.register(Plugin)
class PluginAdmin(ModelAdmin):
    """Admin for installed plugins. Enable/disable without restarting Docker."""

    list_display = ["name", "version", "is_installed", "is_enabled", "updated_at"]
    list_filter = ["is_enabled", "is_installed"]
    search_fields = ["name", "slug"]
    readonly_fields = ["slug", "is_installed", "created_at", "updated_at"]
    list_editable = ["is_enabled"]
    ordering = ["name"]
    inlines = [PluginSettingInline]

    fieldsets = (
        (
            "Plugin Identity",
            {
                "fields": ("name", "slug", "version", "description"),
            },
        ),
        (
            "State",
            {
                "fields": ("is_installed", "is_enabled", "module_path"),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
