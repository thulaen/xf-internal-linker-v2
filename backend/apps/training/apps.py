"""Django AppConfig for apps.training."""

from __future__ import annotations

from django.apps import AppConfig


class TrainingConfig(AppConfig):
    """Configures the offline-training stack app.

    Holds wrappers for L-BFGS-B (pick #41), TPE (#42), Cosine
    Annealing (#43), LambdaLoss (#44), SWA (#45), and OHEM (#46).
    See :mod:`apps.training` for the full layout.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.training"
    label = "training"
    verbose_name = "Offline training stack"
