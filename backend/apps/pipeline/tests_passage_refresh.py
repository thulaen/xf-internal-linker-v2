"""Tests for scheduled passage embedding refresh."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.content.models import ContentItem, Post
from apps.pipeline.services.passage_refresh import refresh_passages


class PassageRefreshTests(TestCase):
    def test_refreshes_only_canonical_items_missing_passage_rows(self) -> None:
        item = ContentItem.objects.create(
            content_id=1,
            content_type="thread",
            title="Needs passages",
        )
        Post.objects.create(content_item=item, raw_bbcode="body", clean_text="body")
        duplicate = ContentItem.objects.create(
            content_id=2,
            content_type="thread",
            title="Duplicate",
            duplicate_of=item,
        )
        Post.objects.create(content_item=duplicate, raw_bbcode="body", clean_text="body")

        with patch(
            "apps.pipeline.services.passage_relevance.regenerate_passage_embeddings_for",
            return_value=3,
        ) as regenerate:
            result = refresh_passages(max_items=10)

        self.assertEqual(result, {"processed": 1, "passages_refreshed": 3})
        regenerate.assert_called_once_with(item)

    def test_non_positive_limit_does_no_work(self) -> None:
        self.assertEqual(refresh_passages(max_items=0), {"processed": 0, "passages_refreshed": 0})
