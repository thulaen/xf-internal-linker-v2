import logging
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
    
    Reconciles the parsed LinkEdge list with the database, adding new links
    and removing ones that no longer exist in the raw BBCode.
    
    Returns:
        Number of links currently active for this item.
    """
    with transaction.atomic():
        # Get current links from this host
        existing_qs = ExistingLink.objects.filter(from_content_item=content_item).select_related("to_content_item")
        
        # Build a map of existing links to aid reconciliation
        # Key: (to_content_id, to_content_type, anchor_text)
        current_map = {
            (el.to_content_item.content_id, el.to_content_item.content_type, el.anchor_text): el
            for el in existing_qs
        }
        
        target_keys = set()
        new_links = []
        
        for edge in edges:
            key = (edge.to_content_id, edge.to_content_type, edge.anchor_text)
            target_keys.add(key)
            
            if key not in current_map:
                # Find the destination ContentItem
                try:
                    to_item = ContentItem.objects.get(
                        content_id=edge.to_content_id,
                        content_type=edge.to_content_type
                    )
                    new_links.append(ExistingLink(
                        from_content_item=content_item,
                        to_content_item=to_item,
                        anchor_text=edge.anchor_text
                    ))
                except ContentItem.DoesNotExist:
                    # Skip links to items we haven't indexed yet
                    continue
        
        # Bulk create new links
        if new_links:
            ExistingLink.objects.bulk_create(new_links, ignore_conflicts=True)
            
        # Delete links that are no longer present
        to_delete_ids = [
            el.pk for key, el in current_map.items() if key not in target_keys
        ]
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
