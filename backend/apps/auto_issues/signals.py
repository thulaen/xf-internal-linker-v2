"""Signal handlers for AutoIssue follow-up history."""

from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import gh_actions_history

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=AutoIssue)
def remember_previous_status(sender, instance: AutoIssue, **kwargs) -> None:
    """Remember whether a GitHub CI issue was already resolved."""
    if not instance.pk or instance.source != AutoIssue.SOURCE_GH_CI:
        instance._gh_actions_was_resolved = False
        return
    prior = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    instance._gh_actions_was_resolved = prior == AutoIssue.STATUS_RESOLVED


@receiver(post_save, sender=AutoIssue)
def append_gh_actions_resolution(sender, instance: AutoIssue, created: bool, **kwargs) -> None:
    """Append a resolved history line when a GitHub CI AutoIssue closes."""
    if created or getattr(instance, "_gh_actions_was_resolved", False):
        return
    if instance.source != AutoIssue.SOURCE_GH_CI or instance.status != AutoIssue.STATUS_RESOLVED:
        return
    try:
        gh_actions_history.append_resolution_history(instance)
    except OSError:
        logger.warning("could not append GitHub Actions resolution history", exc_info=True)
