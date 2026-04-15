"""
Content identity helpers (plan item 21).

``mark_as_checked_if_unchanged`` is the single entry point every importer
should call at the top of its per-item upsert. If the new content hash matches
the stored one, the helper just stamps ``last_checked_at`` and returns True so
the caller can skip the expensive re-embed + version-bump path.

Why centralise it:
  - Every importer (XenForo, WordPress, crawler, etc) needs the same decision.
  - Defining the short-circuit once means every caller gets the same
    behaviour, and we can adjust the rule (e.g. force-revalidate after N days)
    in one place.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


def mark_as_checked_if_unchanged(
    *,
    source_key: str,
    new_content_hash: str,
) -> Optional[bool]:
    """Return True if the short-circuit fired, False if the importer should upsert, None if no prior row.

    Semantics:
      - None  -> no ContentItem exists for ``source_key``. Caller should run
                 the normal full upsert.
      - True  -> the hash is unchanged.  We updated ``last_checked_at`` only.
                 Caller MUST skip re-embedding and MUST NOT bump the version.
      - False -> a row exists but the hash differs.  Caller should run the
                 normal upsert (which will bump content_version and re-embed).

    The helper never raises — if anything goes wrong we return None so the
    caller falls back to the safe full upsert path.
    """
    if not source_key or not new_content_hash:
        return None

    try:
        from apps.content.models import ContentItem

        item = (
            ContentItem.objects.filter(source_key=source_key)
            .only("pk", "content_hash")
            .first()
        )
        if item is None:
            return None

        if item.content_hash == new_content_hash:
            # Stamp last_checked_at only — leave everything else untouched.
            # update_fields keeps this to a single targeted SQL UPDATE.
            ContentItem.objects.filter(pk=item.pk).update(
                last_checked_at=timezone.now()
            )
            return True

        return False

    except Exception:
        logger.warning(
            "mark_as_checked_if_unchanged failed; caller should upsert fully",
            exc_info=True,
        )
        return None
