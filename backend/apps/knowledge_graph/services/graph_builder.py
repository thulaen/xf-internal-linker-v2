import logging
from collections import Counter
from django.db import transaction
from apps.content.models import ContentItem
from apps.knowledge_graph.models import EntityNode, ArticleEntityEdge
from apps.pipeline.services.text_tokens import tokenize_text_batch, STANDARD_ENGLISH_STOPWORDS

logger = logging.getLogger(__name__)

MAX_CHARS = 100000
TOP_N_ENTITIES = 20

def build_knowledge_graph(batch_size=1000):
    """
    Incrementally builds the knowledge graph by extracting entities from ContentItems.
    Skips unchanged content by comparing content_hash.
    """
    logger.info("Starting knowledge graph build...")
    
    # We iterate over all ContentItems that have a Post attached
    queryset = ContentItem.objects.select_related('post').exclude(post__isnull=True)
    
    total_processed = 0
    total_skipped = 0
    
    # Process in chunks
    for start in range(0, queryset.count(), batch_size):
        chunk = queryset[start:start+batch_size]
        
        for item in chunk:
            post = item.post
            if not post or not post.clean_text:
                continue
            
            # The incremental check: if we already have edges for this content with the current hash, skip it.
            current_hash = item.content_hash
            if not current_hash:
                continue
                
            existing_edges = ArticleEntityEdge.objects.filter(content_item=item)
            if existing_edges.exists():
                first_edge = existing_edges.first()
                if first_edge.extraction_version == current_hash:
                    total_skipped += 1
                    continue
            
            # Extract entities using TF-IDF style (basic term frequency for now per user request)
            text_to_process = post.clean_text[:MAX_CHARS]
            
            # Tokenize and drop stopwords
            # tokenize_text_batch expects a list of strings
            token_sets = tokenize_text_batch([text_to_process], STANDARD_ENGLISH_STOPWORDS)
            if not token_sets or not token_sets[0]:
                continue
                
            tokens = list(token_sets[0])
            
            # Since tokenize_text_batch returns a frozenset of unique tokens, we don't have frequencies.
            # We need to count the actual words to get frequency.
            # Let's tokenize manually or use a simple regex to get list of words.
            import re
            words = re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", text_to_process.lower())
            filtered_words = [w for w in words if w not in STANDARD_ENGLISH_STOPWORDS and len(w) >= 3]
            
            word_counts = Counter(filtered_words)
            top_words = word_counts.most_common(TOP_N_ENTITIES)
            
            if not top_words:
                continue
                
            max_count = top_words[0][1]
            
            with transaction.atomic():
                # Clear old edges for this item
                existing_edges.delete()
                
                # Add new edges
                edges_to_create = []
                for word, count in top_words:
                    # Normalized TF weight
                    weight = count / float(max_count)
                    
                    # Get or create EntityNode
                    entity, _ = EntityNode.objects.get_or_create(
                        canonical_form=word,
                        entity_type="keyword",
                        defaults={"surface_form": word}
                    )
                    
                    edges_to_create.append(
                        ArticleEntityEdge(
                            content_item=item,
                            entity=entity,
                            weight=weight,
                            extraction_version=current_hash
                        )
                    )
                
                ArticleEntityEdge.objects.bulk_create(edges_to_create)
                total_processed += 1
                
    logger.info(f"Knowledge graph build complete. Processed: {total_processed}, Skipped: {total_skipped}")

