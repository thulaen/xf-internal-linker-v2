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


def find_cross_source_duplicate(
    *,
    content_hash: str,
    exclude_id: Optional[int] = None,
):
    """Find a canonical ContentItem with the same content hash, if any (Group A.6).

    Used by importers to detect when the same article has already been
    pulled in from a different source (e.g. a forum thread that was also
    re-published as a WordPress post). Returns the existing canonical
    row, or None if no cross-source duplicate exists.

    Plain-English flow:
      1. Importer builds the new ContentItem and computes ``content_hash``.
      2. Importer calls this helper.
      3. If a match comes back, importer sets ``new_item.duplicate_of = match``
         and SKIPS embedding generation — the duplicate reuses the
         canonical's vector via the FK.
      4. If no match, importer proceeds with the normal upsert (and
         embedding generation runs as usual).

    Filters applied:
      - ``content_hash`` must match (exact equality on the SHA-256 hex).
      - The candidate must NOT be soft-deleted (``is_deleted=False``).
      - The candidate must itself BE the canonical row (``duplicate_of__isnull=True``).
        This prevents two duplicates from chaining back through each other.
      - The candidate is not the row we're currently processing (``exclude_id``).

    The helper never raises — defaults to None on any exception so the
    caller falls back to the safe non-deduplicated path.
    """
    if not content_hash:
        return None

    try:
        from apps.content.models import ContentItem

        qs = ContentItem.objects.filter(
            content_hash=content_hash,
            is_deleted=False,
            duplicate_of__isnull=True,
        ).only("pk", "title", "source_key")

        if exclude_id is not None:
            qs = qs.exclude(pk=exclude_id)

        return qs.first()

    except Exception:
        logger.warning(
            "find_cross_source_duplicate failed; caller should treat as no duplicate",
            exc_info=True,
        )
        return None
