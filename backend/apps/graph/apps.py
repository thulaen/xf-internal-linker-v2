"""Graph app — link graph data, PageRank, orphan detection."""

from django.apps import AppConfig


class GraphConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.graph"
    verbose_name = "Link Graph"
