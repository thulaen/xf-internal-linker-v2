from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.content.models import ContentItem
from apps.content.services.clustering import ClusteringService


@receiver(post_save, sender=ContentItem)
def content_item_clustering_trigger(sender, instance, created, **kwargs):
    """
    FR-014: Dynamic clustering trigger.
    Runs whenever an item is saved/updated to ensure it's in the correct cluster.
    """
    # Only run if we have an embedding
    if instance.embedding is not None:
        # We use a service instance to handle logic.
        # In a real high-traffic environment, this would be a Celery task.
        service = ClusteringService()
        # We use transaction.on_commit for safety, but here we can just call it
        # as it's a small internal tool.
        service.update_item_cluster(instance.id)
