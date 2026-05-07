"""
Core admin — AppSetting configuration management.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AppSetting, PasskeyChallenge, PasskeyCredential


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


@admin.register(PasskeyCredential)
class PasskeyCredentialAdmin(ModelAdmin):
    """Browse / debug enrolled passkeys. Binary fields are read-only."""

    list_display = ("user", "label", "sign_count", "last_used_at", "created_at")
    list_filter = ("created_at", "last_used_at")
    search_fields = ("user__username", "label")
    readonly_fields = (
        "credential_id",
        "public_key",
        "sign_count",
        "created_at",
        "updated_at",
    )
    ordering = ("-last_used_at", "-created_at")


@admin.register(PasskeyChallenge)
class PasskeyChallengeAdmin(ModelAdmin):
    """Short-lived (5-min TTL) WebAuthn challenges, mostly auto-pruned."""

    list_display = ("user", "operation_type", "expires_at", "created_at")
    list_filter = ("operation_type", "expires_at")
    readonly_fields = ("challenge", "created_at", "updated_at")
    ordering = ("-created_at",)
