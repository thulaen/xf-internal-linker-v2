import logging
from django.db import transaction, connection
from apps.content.models import ContentItem, ContentCluster

logger = logging.getLogger(__name__)

class ClusteringService:
    """
    Implements FR-014: Near-Duplicate Destination Clustering.
    Uses semantic embeddings (pgvector) to group similar ContentItems.
    """

    def __init__(self, similarity_threshold=0.04):
        # Default 0.04 cosine distance ~= 0.96 cosine similarity
        self.similarity_threshold = similarity_threshold

    def run_clustering_pass(self):
        """Batch job to cluster all items that are currently unclustered."""
        unclustered = ContentItem.objects.filter(cluster__isnull=True).only('id', 'embedding')
        count = unclustered.count()
        logger.info(f"Starting clustering pass for {count} unclustered items.")
        
        for item in unclustered:
            if item.embedding is not None:
                self.update_item_cluster(item.id)

    def update_item_cluster(self, item_id):
        """
        Dynamic clustering update for a single item (e.g. after save).
        Finds near-duplicates and joins/merges clusters accordingly.
        """
        try:
            item = ContentItem.objects.get(id=item_id)
        except ContentItem.DoesNotExist:
            return

        if item.embedding is None:
            return

        import numpy as np
        # 1. Find neighbors within threshold (excluding self)
        # We use a raw SQL query here to avoid RecursionError in some psycopg versions
        # when dealing with large 1024-dimension float arrays in ORM annotations.
        query = """
            SELECT id, cluster_id 
            FROM content_contentitem 
            WHERE id != %s 
              AND embedding IS NOT NULL
              AND embedding <=> %s::vector < %s
        """
        # Convert embedding to list to ensure it's serializable if it's a Vector or array
        emb_list = list(item.embedding) if hasattr(item.embedding, '__iter__') else item.embedding
        
        with connection.cursor() as cursor:
            cursor.execute(query, [item.id, emb_list, self.similarity_threshold])
            rows = cursor.fetchall()
        
        neighbor_ids = [r[0] for r in rows]
        neighbor_cluster_ids = set(r[1] for r in rows if r[1] is not None)
        
        # 2. Collect existing clusters from neighbors
        existing_clusters = list(ContentCluster.objects.filter(id__in=neighbor_cluster_ids))
        
        with transaction.atomic():
            # Re-query inside transaction to avoid race conditions
            neighbors_no_cluster = ContentItem.objects.select_for_update().filter(
                id__in=neighbor_ids, cluster__isnull=True
            )

            if not existing_clusters:
                # Join with neighbors that have no cluster?
                # If neighbors have no clusters, we should create one and add them all.
                no_cluster_ids = list(neighbors_no_cluster.values_list('id', flat=True))
                if no_cluster_ids:
                    new_cluster = ContentCluster.objects.create()
                    item.cluster = new_cluster
                    item.save(update_fields=['cluster'])
                    ContentItem.objects.filter(id__in=no_cluster_ids).update(cluster=new_cluster)
                    self.elect_canonical(new_cluster.id)
                else:
                    # No near-duplicates, item stays unclustered (or in its own cluster if we prefer)
                    # Requirement says "Cluster near-duplicate", so solo items don't need clusters.
                    pass
            elif len(existing_clusters) == 1:
                # Join the single existing cluster
                target_cluster = list(existing_clusters)[0]
                if target_cluster.is_manually_fixed:
                    logger.debug(f"Item {item.id} matched manually fixed cluster {target_cluster.id}. Joining.")
                item.cluster = target_cluster
                item.save(update_fields=['cluster'])
                self.elect_canonical(target_cluster.id)
            else:
                # Multiple clusters found -> Merge them
                target_cluster = self.merge_clusters([c.id for c in existing_clusters])
                item.cluster = target_cluster
                item.save(update_fields=['cluster'])
                self.elect_canonical(target_cluster.id)

    def merge_clusters(self, cluster_ids):
        """Merges multiple clusters into one (the first one) and re-elects canonical."""
        if not cluster_ids:
            return None
        
        main_cluster_id = cluster_ids[0]
        other_cluster_ids = cluster_ids[1:]
        
        # Check if any other cluster is manually fixed - if so, it should probably be the main one
        fixed_clusters = ContentCluster.objects.filter(id__in=cluster_ids, is_manually_fixed=True)
        if fixed_clusters.exists():
            main_cluster_id = fixed_clusters.first().id
            other_cluster_ids = [cid for cid in cluster_ids if cid != main_cluster_id]

        # Move all members to the main cluster
        ContentItem.objects.filter(cluster_id__in=other_cluster_ids).update(cluster_id=main_cluster_id)
        
        # Delete old clusters
        ContentCluster.objects.filter(id__in=other_cluster_ids).delete()
        
        return ContentCluster.objects.get(id=main_cluster_id)

    def elect_canonical(self, cluster_id):
        """
        Picks the canonical representative for a cluster based on priority.
        1. Authority (PageRank)
        2. Velocity
        3. Type priority: resource > thread > wp_post
        """
        cluster = ContentCluster.objects.get(id=cluster_id)
        if cluster.is_manually_fixed and cluster.canonical_item_id:
            # Respect manual choice
            ContentItem.objects.filter(cluster=cluster).update(is_canonical=False)
            ContentItem.objects.filter(id=cluster.canonical_item_id).update(is_canonical=True)
            return

        members = ContentItem.objects.filter(cluster=cluster).order_by(
            '-march_2026_pagerank_score',
            '-velocity_score'
        )

        # source priority sort (manual python sort as it's small)
        def get_type_priority(ctype):
            prio = {"resource": 3, "thread": 2, "wp_post": 1}
            return prio.get(ctype, 0)

        if not members.exists():
            return None

        best_item = sorted(members, key=lambda x: get_type_priority(x.content_type), reverse=True)[0]

        with transaction.atomic():
            ContentItem.objects.filter(cluster=cluster).update(is_canonical=False)
            best_item.is_canonical = True
            best_item.save(update_fields=['is_canonical'])
            
            cluster.canonical_item = best_item
            cluster.save(update_fields=['canonical_item'])
        
        return best_item
