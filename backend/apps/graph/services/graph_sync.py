import logging
from collections import defaultdict
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.content.models import ContentItem
from apps.graph.models import ExistingLink, LinkFreshnessEdge
from apps.pipeline.services.link_parser import LinkEdge, extract_internal_links

logger = logging.getLogger(__name__)


def sync_existing_links(
    content_item: ContentItem,
    edges: list[LinkEdge],
    *,
    allow_disappearance: bool = True,
    tracked_at=None,
) -> int:
    """Python reference implementation for one host item's graph state."""
    return _sync_existing_links_py(
        content_item,
        edges,
        allow_disappearance=allow_disappearance,
        tracked_at=tracked_at,
    )


def sync_existing_links_for_content_item(
    content_item: ContentItem,
    raw_bbcode: str,
    *,
    allow_disappearance: bool = True,
    tracked_at=None,
) -> int:
    tracked_at = tracked_at or timezone.now()
    if _runtime_owner_for_graph_sync() == "csharp":
        return _sync_existing_links_via_http_worker(
            content_item,
            raw_bbcode,
            allow_disappearance=allow_disappearance,
            tracked_at=tracked_at,
        )

    edges = extract_internal_links(
        raw_bbcode,
        content_item.content_id,
        content_item.content_type,
        forum_domains=_internal_domains(),
    )
    return _sync_existing_links_py(
        content_item,
        edges,
        allow_disappearance=allow_disappearance,
        tracked_at=tracked_at,
    )


def _sync_existing_links_py(
    content_item: ContentItem,
    edges: list[LinkEdge],
    *,
    allow_disappearance: bool = True,
    tracked_at=None,
) -> int:
    """
    Update ExistingLink records for a single host ContentItem.

    Reconciles the parsed LinkEdge list with the database, adding new links,
    updating retained links in place, and removing ones that no longer exist
    in the raw source content.

    Args:
        allow_disappearance: When False, missing edges do not create disappearance
            events. This is used for non-body sync paths.
        tracked_at: Optional timestamp used for first_seen/last_seen updates.

    Returns:
        Number of links currently active for this item.
    """
    tracked_at = tracked_at or timezone.now()
    with transaction.atomic():
        existing_qs = (
            ExistingLink.objects.filter(from_content_item=content_item)
            .select_related("to_content_item")
            .order_by("pk")
        )

        current_map: dict[tuple[int, str], list[ExistingLink]] = defaultdict(list)
        for existing_link in existing_qs:
            current_map[
                (
                    existing_link.to_content_item.content_id,
                    existing_link.to_content_item.content_type,
                )
            ].append(existing_link)

        destination_ids_by_type: dict[str, set[int]] = defaultdict(set)
        for edge in edges:
            destination_ids_by_type[edge.to_content_type].add(edge.to_content_id)

        destination_map: dict[tuple[int, str], ContentItem] = {}
        for content_type, content_ids in destination_ids_by_type.items():
            for destination in ContentItem.objects.filter(
                content_type=content_type,
                content_id__in=content_ids,
            ):
                destination_map[(destination.content_id, destination.content_type)] = (
                    destination
                )

        target_keys: set[tuple[int, str]] = set()
        new_links: list[ExistingLink] = []
        updated_links: list[ExistingLink] = []
        duplicate_ids_to_delete: list[int] = []

        for edge in edges:
            key = (edge.to_content_id, edge.to_content_type)
            target_keys.add(key)

            current_links = current_map.get(key, [])
            if current_links:
                primary = current_links[0]
                duplicate_ids_to_delete.extend(link.pk for link in current_links[1:])
                changed = False
                for field_name in [
                    "anchor_text",
                    "extraction_method",
                    "link_ordinal",
                    "source_internal_link_count",
                    "context_class",
                ]:
                    value = getattr(edge, field_name)
                    if getattr(primary, field_name) != value:
                        setattr(primary, field_name, value)
                        changed = True
                if changed:
                    updated_links.append(primary)
                continue

            to_item = destination_map.get(key)
            if to_item is None:
                continue
            new_links.append(
                ExistingLink(
                    from_content_item=content_item,
                    to_content_item=to_item,
                    anchor_text=edge.anchor_text,
                    extraction_method=edge.extraction_method,
                    link_ordinal=edge.link_ordinal,
                    source_internal_link_count=edge.source_internal_link_count,
                    context_class=edge.context_class,
                )
            )

        if new_links:
            ExistingLink.objects.bulk_create(new_links)

        if updated_links:
            ExistingLink.objects.bulk_update(
                updated_links,
                [
                    "anchor_text",
                    "extraction_method",
                    "link_ordinal",
                    "source_internal_link_count",
                    "context_class",
                ],
            )

        to_delete_ids = list(duplicate_ids_to_delete)
        if allow_disappearance:
            for key, current_links in current_map.items():
                if key in target_keys:
                    continue
                to_delete_ids.extend(link.pk for link in current_links)

        if to_delete_ids:
            ExistingLink.objects.filter(pk__in=to_delete_ids).delete()

        _sync_link_freshness_edges(
            content_item=content_item,
            edges=edges,
            destination_map=destination_map,
            allow_disappearance=allow_disappearance,
            tracked_at=tracked_at,
        )

    return len(target_keys)


def refresh_existing_links(*, tracked_at=None) -> int:
    tracked_at = tracked_at or timezone.now()
    if _runtime_owner_for_graph_sync() == "csharp":
        return _refresh_existing_links_via_http_worker(tracked_at=tracked_at)
    return _refresh_existing_links_py(tracked_at=tracked_at)


def _refresh_existing_links_py(*, tracked_at=None) -> int:
    """Rebuild existing-link edges for all indexed content with stored bodies."""
    content_items = (
        ContentItem.objects.select_related("post")
        .filter(is_deleted=False, post__raw_bbcode__gt="")
        .order_by("pk")
    )
    internal_domains = _internal_domains()
    refreshed = 0
    tracked_at = tracked_at or timezone.now()

    CHUNK_SIZE = 100
    chunk: list[tuple] = []

    def _flush_chunk(chunk: list[tuple]) -> int:
        # Wrapping each 100-item chunk in one transaction reduces per-row commit
        # overhead from O(N) to O(N/100) and prevents partial-graph corruption
        # if the process is killed mid-batch.
        with transaction.atomic():
            for content_item, edges in chunk:
                sync_existing_links(
                    content_item,
                    edges,
                    allow_disappearance=True,
                    tracked_at=tracked_at,
                )
        return len(chunk)

    for content_item in content_items.iterator(chunk_size=CHUNK_SIZE):
        post = getattr(content_item, "post", None)
        if post is None or not post.raw_bbcode:
            continue
        edges = extract_internal_links(
            post.raw_bbcode,
            content_item.content_id,
            content_item.content_type,
            forum_domains=internal_domains,
        )
        chunk.append((content_item, edges))
        if len(chunk) >= CHUNK_SIZE:
            refreshed += _flush_chunk(chunk)
            chunk = []

    if chunk:
        refreshed += _flush_chunk(chunk)

    return refreshed


def _sync_link_freshness_edges(
    *,
    content_item: ContentItem,
    edges: list[LinkEdge],
    destination_map: dict[tuple[int, str], ContentItem],
    allow_disappearance: bool,
    tracked_at,
) -> None:
    history_qs = (
        LinkFreshnessEdge.objects.filter(from_content_item=content_item)
        .select_related("to_content_item")
        .order_by("pk")
    )
    history_map = {
        (row.to_content_item.content_id, row.to_content_item.content_type): row
        for row in history_qs
    }

    to_create: list[LinkFreshnessEdge] = []
    to_update: list[LinkFreshnessEdge] = []
    target_keys: set[tuple[int, str]] = set()

    for edge in edges:
        key = (edge.to_content_id, edge.to_content_type)
        target_keys.add(key)
        destination = destination_map.get(key)
        if destination is None:
            continue

        history_row = history_map.get(key)
        if history_row is None:
            to_create.append(
                LinkFreshnessEdge(
                    from_content_item=content_item,
                    to_content_item=destination,
                    first_seen_at=tracked_at,
                    last_seen_at=tracked_at,
                    is_active=True,
                )
            )
            continue

        changed = False
        if history_row.first_seen_at is None:
            history_row.first_seen_at = tracked_at
            changed = True
        if history_row.last_seen_at != tracked_at:
            history_row.last_seen_at = tracked_at
            changed = True
        if not history_row.is_active:
            history_row.is_active = True
            changed = True
        if changed:
            to_update.append(history_row)

    if allow_disappearance:
        for key, history_row in history_map.items():
            if key in target_keys or not history_row.is_active:
                continue
            history_row.is_active = False
            history_row.last_disappeared_at = tracked_at
            to_update.append(history_row)

    if to_create:
        LinkFreshnessEdge.objects.bulk_create(to_create)

    if to_update:
        deduped_updates: dict[int, LinkFreshnessEdge] = {}
        for row in to_update:
            if row.pk is not None:
                deduped_updates[row.pk] = row
        LinkFreshnessEdge.objects.bulk_update(
            list(deduped_updates.values()),
            ["first_seen_at", "last_seen_at", "last_disappeared_at", "is_active"],
        )


def _internal_domains() -> list[str]:
    domains: list[str] = []
    for raw_url in [
        getattr(settings, "XENFORO_BASE_URL", ""),
        getattr(settings, "WORDPRESS_BASE_URL", ""),
    ]:
        host = urlparse(raw_url).netloc.strip().lower()
        if host and host not in domains:
            domains.append(host)
    return domains


def _runtime_owner_for_graph_sync() -> str:
    from apps.pipeline.tasks import _runtime_owner_for_lane

    return _runtime_owner_for_lane("graph_sync")


def _sync_existing_links_via_http_worker(
    content_item: ContentItem,
    raw_bbcode: str,
    *,
    allow_disappearance: bool,
    tracked_at,
) -> int:
    from apps.graph.services.http_worker_client import sync_graph_content

    result = sync_graph_content(
        content_item_pk=content_item.pk,
        content_id=content_item.content_id,
        content_type=content_item.content_type,
        raw_bbcode=raw_bbcode,
        forum_domains=_internal_domains(),
        allow_disappearance=allow_disappearance,
        tracked_at=tracked_at,
    )
    return int(result.get("active_links") or 0)


def _refresh_existing_links_via_http_worker(*, tracked_at) -> int:
    from apps.graph.services.http_worker_client import refresh_graph_links

    result = refresh_graph_links(
        forum_domains=_internal_domains(),
        tracked_at=tracked_at,
    )
    return int(result.get("refreshed_items") or 0)
