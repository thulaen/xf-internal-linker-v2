import logging
from django.db import transaction
from apps.content.models import ContentItem
from apps.graph.models import ExistingLink
from apps.pipeline.services.link_parser import LinkEdge

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
