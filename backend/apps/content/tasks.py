"""Celery task definitions for the content app."""

from celery import shared_task
import logging
from apps.content.services.clustering import ClusteringService
from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)


@shared_task(
    name="content.cluster_items",
    time_limit=300,
    soft_time_limit=270,
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
)
def cluster_items(item_ids: list[int]) -> dict:
    """Trigger clustering logic for a batch of recently imported/updated items."""
    service = ClusteringService()
    count = 0
    failed_ids = []
    for item_id in item_ids:
        try:
            service.update_item_cluster(item_id)
            count += 1
        except Exception:
            logger.exception("Failed to cluster item %s", item_id)
            failed_ids.append(item_id)
    return {"clustered_count": count, "failed_ids": failed_ids}
