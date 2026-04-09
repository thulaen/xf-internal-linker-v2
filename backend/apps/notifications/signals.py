"""
Signals for the notifications app.

Wires ErrorLog creation to emit_operator_alert so every new backend
error automatically surfaces as an operator alert.
"""

import logging

from django.db.models.signals import post_save

logger = logging.getLogger(__name__)


def _on_error_log_created(sender, instance, created: bool, **kwargs) -> None:
    """Emit an operator alert whenever a new ErrorLog row is created."""
    if not created:
        return
    try:
        from apps.notifications.models import OperatorAlert
        from apps.notifications.services import emit_operator_alert

        emit_operator_alert(
            event_type="error.logged",
            severity=OperatorAlert.SEVERITY_ERROR,
            title=f"Background job error: {instance.job_type}",
            message=instance.error_message[:300]
            if instance.error_message
            else "An error was recorded.",
            source_area=OperatorAlert.AREA_JOBS,
            dedupe_key=f"error.logged:{instance.pk}",
            related_route="/jobs",
            payload={
                "job_type": instance.job_type,
                "step": instance.step,
            },
            error_log_id=instance.pk,
        )
    except Exception:
        logger.warning("_on_error_log_created: failed to emit alert", exc_info=True)


def connect_signals() -> None:
    """Connect all notification signals. Called from NotificationsConfig.ready()."""
    from apps.audit.models import ErrorLog

    post_save.connect(
        _on_error_log_created,
        sender=ErrorLog,
        dispatch_uid="notifications.error_log_created",
    )
