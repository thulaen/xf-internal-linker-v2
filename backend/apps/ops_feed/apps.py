"""Django AppConfig for the Operations Feed."""

from django.apps import AppConfig


class OpsFeedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ops_feed"
    verbose_name = "Operations Feed"
