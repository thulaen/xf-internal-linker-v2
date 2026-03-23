"""
Graph admin — ExistingLink (the live link graph topology).
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import ExistingLink


@admin.register(ExistingLink)
class ExistingLinkAdmin(ModelAdmin):
    """Admin for links that already exist on the live forum."""

    list_display = ["from_content_item", "to_content_item", "anchor_preview", "discovered_at"]
    search_fields = [
        "from_content_item__title", "to_content_item__title", "anchor_text",
    ]
    readonly_fields = ["from_content_item", "to_content_item", "anchor_text", "discovered_at"]
    ordering = ["-discovered_at"]
    list_per_page = 100

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    @admin.display(description="Anchor Text")
    def anchor_preview(self, obj: ExistingLink) -> str:
        return obj.anchor_text[:60] if obj.anchor_text else "—"
