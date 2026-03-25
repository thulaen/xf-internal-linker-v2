import logging
from collections import defaultdict
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction

from apps.content.models import ContentItem
from apps.graph.models import ExistingLink
from apps.pipeline.services.link_parser import LinkEdge, extract_internal_links

logger = logging.getLogger(__name__)

def sync_existing_links(content_item: ContentItem, edges: list[LinkEdge]) -> int:
    """
    Update ExistingLink records for a single host ContentItem.

    Reconciles the parsed LinkEdge list with the database, adding new links,
    updating retained links in place, and removing ones that no longer exist
    in the raw source content.

    Returns:
        Number of links currently active for this item.
    """
    with transaction.atomic():
        existing_qs = (
            ExistingLink.objects
            .filter(from_content_item=content_item)
            .select_related("to_content_item")
            .order_by("pk")
        )

        current_map: dict[tuple[int, str], list[ExistingLink]] = defaultdict(list)
        for existing_link in existing_qs:
            current_map[
                (existing_link.to_content_item.content_id, existing_link.to_content_item.content_type)
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
                destination_map[(destination.content_id, destination.content_type)] = destination

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
            new_links.append(ExistingLink(
                from_content_item=content_item,
                to_content_item=to_item,
                anchor_text=edge.anchor_text,
                extraction_method=edge.extraction_method,
                link_ordinal=edge.link_ordinal,
                source_internal_link_count=edge.source_internal_link_count,
                context_class=edge.context_class,
            ))

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
        for key, current_links in current_map.items():
            if key in target_keys:
                continue
            to_delete_ids.extend(link.pk for link in current_links)

        if to_delete_ids:
            ExistingLink.objects.filter(pk__in=to_delete_ids).delete()

    return len(target_keys)


def refresh_existing_links() -> int:
    """Rebuild existing-link edges for all indexed content with stored bodies."""
    content_items = (
        ContentItem.objects
        .select_related("post")
        .filter(is_deleted=False, post__raw_bbcode__gt="")
        .order_by("pk")
    )
    internal_domains = _internal_domains()
    refreshed = 0

    for content_item in content_items.iterator(chunk_size=100):
        post = getattr(content_item, "post", None)
        if post is None or not post.raw_bbcode:
            continue
        edges = extract_internal_links(
            post.raw_bbcode,
            content_item.content_id,
            content_item.content_type,
            forum_domains=internal_domains,
        )
        sync_existing_links(content_item, edges)
        refreshed += 1

    return refreshed


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
