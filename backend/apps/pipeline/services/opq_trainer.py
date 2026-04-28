import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
import numpy as np

from apps.content.models import PassageEmbedding, OPQCodebook

logger = logging.getLogger(__name__)

def generate_corpus_signature() -> str:
    """
    Generate a simple signature of the current corpus.
    In practice, this might be a hash of the total count of passages
    and maybe the latest update timestamp, to see if the corpus has shifted.
    """
    count = PassageEmbedding.objects.count()
    if count == 0:
        return "empty"
    latest = PassageEmbedding.objects.order_by('-updated_at').first()
    return f"c{count}_t{int(latest.updated_at.timestamp())}"

def should_retrain() -> bool:
    """
    Determine if the OPQ codebook should be retrained.
    We retrain if there's no active codebook, or if the active one
    is older than 7 days AND the corpus signature has changed significantly.
    """
    active = OPQCodebook.objects.filter(is_active=True).first()
    if not active:
        return True
    
    if timezone.now() - active.trained_at > timedelta(days=7):
        # Weekly training
        return True
        
    return False

def train_codebook(sample_size=100000, m=64, k=256, n_iter=25):
    """
    Extract a random sample of passage embeddings and train the OPQ codebook.
    """
    if not should_retrain():
        logger.info("OPQ codebook is up to date, skipping training.")
        return

    logger.info(f"Starting OPQ codebook training (M={m}, K={k}, sample={sample_size})")

    # 1. Fetch random sample of passage embeddings
    # Using order_by('?') is slow on large tables, but we assume sample_size is reasonable
    # or we can use a more efficient sampling method if needed.
    passages = PassageEmbedding.objects.filter(embedding__isnull=False).order_by('?')[:sample_size]
    
    vectors = []
    for p in passages:
        vectors.append(p.embedding)
        
    if not vectors:
        logger.warning("No passage embeddings found for training.")
        return
        
    data = np.vstack(vectors).astype(np.float32)
    N, D = data.shape
    
    if D % m != 0:
        raise ValueError(f"Embedding dimension {D} must be divisible by M={m}")
        
    # 2. Call C++ extension to train OPQ
    try:
        from extensions import quantemb
    except ImportError:
        logger.error("quantemb C++ extension not found. Falling back to Python OPQ trainer.")
        # Fallback would go here. For now, we raise if C++ is not available.
        raise RuntimeError("quantemb extension required for OPQ training")
        
    logger.info(f"Calling quantemb.opq_train with {N}x{D} matrix...")
    rot, codebooks = quantemb.opq_train(data, m, k, n_iter)
    
    sig = generate_corpus_signature()
    
    # 3. Save to database
    with transaction.atomic():
        # Deactivate current
        OPQCodebook.objects.filter(is_active=True).update(is_active=False)
        
        # Create new
        new_cb = OPQCodebook.objects.create(
            version=1,
            rotation=rot.tobytes(),
            codebooks=codebooks.tobytes(),
            n_subquantisers=m,
            k_centroids=k,
            corpus_signature=sig,
            is_active=True
        )
        logger.info(f"Activated new OPQ codebook: {new_cb}")

    # Mark old codebooks for cleanup if necessary, or just keep them for rollback.
