"""Signal handlers for paper trail.

When an AutoIssue is resolved AND a PaperTrailEntry links to it via
`linked_autoissue_id`, the linked entry is auto-resolved with the
AutoIssue's `lessons_learned` copied into `resolution_lessons`. This
keeps the two tables in sync so the operator never has to resolve the
same thing twice.

Lifted as a separate module so apps.py can guard the import behind the
lightweight-management-command check (signals would otherwise fire during
heavy app startup paths like `manage.py shell` or `runserver`).
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="auto_issues.AutoIssue")
def propagate_autoissue_resolution(sender, instance, created, **kwargs) -> None:
    """Auto-resolve linked PaperTrailEntry rows when an AutoIssue is closed."""
    if created:
        return
    if instance.status != "resolved":
        return
    # Lazy import to avoid AppRegistryNotReady at module load.
    from apps.paper_trail.models import PaperTrailEntry

    qs = PaperTrailEntry.objects.filter(
        linked_autoissue_id=instance.id,
        status__in=PaperTrailEntry._ACTIVE_STATUSES,
    )
    for entry in qs:
        lessons = (instance.lessons_learned or "").strip()
        if "Trap:" in lessons and "Fix shape:" in lessons:
            entry.status = PaperTrailEntry.STATUS_RESOLVED
            entry.resolved_at = instance.resolved_at
            entry.resolved_by = instance.resolved_by or "auto-propagated"
            entry.resolution_lessons = lessons
            try:
                entry.save()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to auto-propagate AutoIssue #%s -> PaperTrailEntry #%s",
                    instance.id,
                    entry.id,
                    exc_info=True,
                )
