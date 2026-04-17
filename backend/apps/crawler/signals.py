"""
Realtime broadcast signals for the crawler app.

Phase R1.2 of the master plan. `CrawlSession` rows change state often
during an active crawl (pending → running → paused → completed / failed).
Before this wiring, the frontend polled every 5 seconds to catch those
transitions. Now the transitions push instantly via the `crawler.sessions`
topic.

Intentionally scoped:
- Broadcasts `CrawlSession` lifecycle changes ONLY.
- Does NOT broadcast each `CrawledPageMeta` row — that would be per-page
  chatter during a 10k-URL crawl. If per-page freshness becomes a
  requirement (Health page), add a throttled batch broadcast then, not
  per-row.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.realtime.services import broadcast

from .models import CrawlSession
from .serializers import CrawlSessionSerializer

logger = logging.getLogger(__name__)

TOPIC = "crawler.sessions"


@receiver(post_save, sender=CrawlSession, dispatch_uid="realtime.crawl_session.saved")
def _on_crawl_session_saved(
    sender, instance: CrawlSession, created: bool, **kwargs: object
) -> None:
    broadcast(
        TOPIC,
        event="session.created" if created else "session.updated",
        payload=CrawlSessionSerializer(instance).data,
    )


@receiver(
    post_delete, sender=CrawlSession, dispatch_uid="realtime.crawl_session.deleted"
)
def _on_crawl_session_deleted(sender, instance: CrawlSession, **kwargs: object) -> None:
    broadcast(
        TOPIC,
        event="session.deleted",
        payload={"session_id": str(instance.session_id)},
    )
