import uuid
from django.db import models
from apps.content.models import ContentItem

class EntityNode(models.Model):
    ENTITY_TYPES = (
        ('keyword', 'Keyword'),
        ('named_entity', 'Named Entity'),
        ('topic_tag', 'Topic Tag'),
    )

    entity_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    surface_form = models.CharField(max_length=255, db_index=True)
    canonical_form = models.CharField(max_length=255, db_index=True)
    entity_type = models.CharField(max_length=50, choices=ENTITY_TYPES, default='keyword')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('canonical_form', 'entity_type')
        indexes = [
            models.Index(fields=['canonical_form', 'entity_type']),
        ]

    def __str__(self):
        return f"{self.canonical_form} ({self.entity_type})"


class ArticleEntityEdge(models.Model):
    content_item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name='entity_edges')
    entity = models.ForeignKey(EntityNode, on_delete=models.CASCADE, related_name='article_edges')
    weight = models.FloatField(default=0.0)
    extraction_version = models.CharField(max_length=50)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('content_item', 'entity')
        indexes = [
            models.Index(fields=['extraction_version']),
        ]

    def __str__(self):
        return f"{self.content_item} -> {self.entity} ({self.weight})"
