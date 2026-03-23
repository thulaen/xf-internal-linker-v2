"""
Content models — XenForo threads/posts/sentences with pgvector embeddings.
Phase 1 will add full field definitions. This is the scaffold.
"""

from django.db import models
from apps.core.models import TimestampedModel


class ContentItem(TimestampedModel):
    """
    A XenForo thread or resource that can be a link destination.
    Stores the distilled text used for semantic matching and its embedding vector.
    Full field definitions added in Phase 1.
    """

    class Meta:
        verbose_name = "Content Item"
        verbose_name_plural = "Content Items"

    def __str__(self) -> str:
        return f"ContentItem(id={self.pk})"
