"""
Content admin — ScopeItem, ContentItem, Post, Sentence, ContentMetricSnapshot.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import ContentItem, ContentMetricSnapshot, Post, Sentence, ScopeItem, SiloGroup


@admin.register(SiloGroup)
class SiloGroupAdmin(ModelAdmin):
    """Admin for topical silo groups."""

    list_display = ["name", "slug", "display_order", "updated_at"]
    search_fields = ["name", "slug", "description"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["display_order", "name"]

    fieldsets = (
        ("Identity", {
            "fields": ("name", "slug", "description"),
        }),
        ("Display", {
            "fields": ("display_order",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


class SentenceInline(TabularInline):
    """Inline list of sentences extracted from a post."""

    model = Sentence
    fields = ["position", "word_position", "text", "char_count"]
    readonly_fields = ["position", "word_position", "text", "char_count"]
    extra = 0
    can_delete = False
    max_num = 0
    show_change_link = False


class PostInline(TabularInline):
    """Inline post body preview inside a ContentItem."""

    model = Post
    fields = ["word_count", "char_count", "xf_post_id", "last_edit_date"]
    readonly_fields = ["word_count", "char_count", "xf_post_id", "last_edit_date"]
    extra = 0
    can_delete = False
    max_num = 1


@admin.register(ScopeItem)
class ScopeItemAdmin(ModelAdmin):
    """Admin for XenForo forum nodes and resource categories."""

    list_display = ["title", "scope_type", "scope_id", "silo_group", "is_enabled", "content_count", "parent"]
    list_filter = ["scope_type", "is_enabled", "silo_group"]
    search_fields = ["title", "scope_id"]
    readonly_fields = ["created_at", "updated_at"]
    list_editable = ["is_enabled"]
    ordering = ["scope_type", "display_order", "title"]

    fieldsets = (
        ("Identity", {
            "fields": ("scope_id", "scope_type", "title", "parent", "silo_group"),
        }),
        ("Settings", {
            "fields": ("is_enabled", "display_order", "content_count"),
        }),
        ("Extra Data", {
            "fields": ("metadata",),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(ContentItem)
class ContentItemAdmin(ModelAdmin):
    """
    Admin for XenForo content items (threads and resources).
    The central entity of the whole application.
    """

    list_display = [
        "title", "content_type", "scope", "pagerank_score",
        "velocity_score", "view_count", "reply_count", "post_date",
        "is_deleted",
    ]
    list_filter = ["content_type", "is_deleted", "scope__scope_type", "scope"]
    search_fields = ["title", "content_id"]
    readonly_fields = [
        "content_id", "content_type", "content_hash",
        "pagerank_score", "velocity_score",
        "created_at", "updated_at", "fetched_at",
    ]
    list_per_page = 50
    ordering = ["-pagerank_score"]
    inlines = [PostInline]

    fieldsets = (
        ("Content Identity", {
            "fields": ("content_id", "content_type", "title", "url", "scope"),
        }),
        ("NLP / Distillation", {
            "fields": ("distilled_text", "distill_method"),
            "classes": ("collapse",),
        }),
        ("Scores", {
            "fields": ("pagerank_score", "velocity_score"),
            "classes": ("collapse",),
        }),
        ("Engagement", {
            "fields": ("view_count", "reply_count", "download_count", "post_date", "last_post_date"),
            "classes": ("collapse",),
        }),
        ("XenForo IDs", {
            "fields": ("xf_post_id", "xf_update_id", "content_hash"),
            "classes": ("collapse",),
        }),
        ("Status", {
            "fields": ("is_deleted", "fetched_at"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Post)
class PostAdmin(ModelAdmin):
    """Admin for first-post bodies."""

    list_display = ["content_item", "word_count", "char_count", "xf_post_id", "updated_at"]
    search_fields = ["content_item__title"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [SentenceInline]

    fieldsets = (
        ("Content", {
            "fields": ("content_item", "clean_text"),
        }),
        ("Stats", {
            "fields": ("word_count", "char_count"),
        }),
        ("Raw Data", {
            "fields": ("raw_bbcode",),
            "classes": ("collapse",),
        }),
        ("XenForo IDs", {
            "fields": ("xf_post_id", "xf_update_id", "last_edit_date"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Sentence)
class SentenceAdmin(ModelAdmin):
    """Admin for individual sentences extracted by spaCy."""

    list_display = ["content_item", "position", "word_position", "char_count", "text_preview"]
    list_filter = []
    search_fields = ["content_item__title", "text"]
    readonly_fields = ["content_item", "post", "position", "word_position",
                       "start_char", "end_char", "char_count"]
    ordering = ["content_item", "position"]
    list_per_page = 100

    fieldsets = (
        ("Location", {
            "fields": ("content_item", "post", "position", "word_position"),
        }),
        ("Text", {
            "fields": ("text", "char_count", "start_char", "end_char"),
        }),
    )

    @admin.display(description="Text Preview")
    def text_preview(self, obj: Sentence) -> str:
        return obj.text[:100] + "…" if len(obj.text) > 100 else obj.text


@admin.register(ContentMetricSnapshot)
class ContentMetricSnapshotAdmin(ModelAdmin):
    """Admin for historical metric snapshots (used for velocity scoring)."""

    list_display = ["content_item", "captured_at", "view_count", "reply_count", "is_deleted"]
    list_filter = ["is_deleted"]
    search_fields = ["content_item__title", "import_job_id"]
    readonly_fields = ["content_item", "import_job_id", "captured_at"]
    ordering = ["-captured_at"]
