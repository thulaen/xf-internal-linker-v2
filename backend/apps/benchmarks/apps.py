"""Django AppConfig for the benchmarks app."""

from django.apps import AppConfig


class BenchmarksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.benchmarks"
    verbose_name = "Benchmarks"
