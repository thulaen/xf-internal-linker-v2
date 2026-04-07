from celery import shared_task
import logging
from apps.content.services.clustering import ClusteringService

logger = logging.getLogger(__name__)

@shared_task(name="content.cluster_items", time_limit=300, soft_time_limit=270)
def cluster_items(item_ids: list[int]) -> dict:
    """Trigger clustering logic for a batch of recently imported/updated items."""
    service = ClusteringService()
    count = 0
    for item_id in item_ids:
        try:
            service.update_item_cluster(item_id)
            count += 1
        except Exception as exc:
            logger.exception("Failed to cluster item %s", item_id)
    return {"clustered_count": count}
