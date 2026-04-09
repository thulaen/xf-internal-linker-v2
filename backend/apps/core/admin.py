"""
Core admin — AppSetting configuration management.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AppSetting


@admin.register(AppSetting)
class AppSettingAdmin(ModelAdmin):
    """
    Admin for application-wide settings.
    Grouped by category with secret values masked.
    """

    list_display = [
        "key",
        "category",
        "value_type",
        "masked_value",
        "is_secret",
        "updated_at",
    ]
    list_filter = ["category", "value_type", "is_secret"]
    search_fields = ["key", "description"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["category", "key"]

    fieldsets = (
        (
            "Setting Identity",
            {
                "fields": ("key", "category", "description"),
            },
        ),
        (
            "Value",
            {
                "fields": ("value", "value_type", "is_secret"),
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

    @admin.display(description="Value")
    def masked_value(self, obj: AppSetting) -> str:
        """Mask secret values in the list view."""
        if obj.is_secret:
            return "••••••••"
        return obj.value[:80] if len(obj.value) > 80 else obj.value
