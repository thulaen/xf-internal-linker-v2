"""Content admin — registered in Phase 1 with full field definitions."""

from django.contrib import admin
from .models import ContentItem


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    """Admin view for XenForo content items (threads, resources)."""

    list_display = ("pk", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")
