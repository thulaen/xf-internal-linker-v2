from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.content.models import ContentItem, Post, ScopeItem, Sentence, SiloGroup
from apps.suggestions.models import Suggestion


class SuggestionSiloApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="reviewer", password="pass")
        self.client.force_authenticate(user=user)

        silo_a = SiloGroup.objects.create(name="Silo A", slug="silo-a")
        silo_b = SiloGroup.objects.create(name="Silo B", slug="silo-b")
        scope_a = ScopeItem.objects.create(scope_id=1, scope_type="node", title="A", silo_group=silo_a)
        scope_a_host = ScopeItem.objects.create(scope_id=2, scope_type="node", title="A Host", silo_group=silo_a)
        scope_b = ScopeItem.objects.create(scope_id=3, scope_type="node", title="B", silo_group=silo_b)
        scope_unassigned = ScopeItem.objects.create(scope_id=4, scope_type="node", title="Loose")

        dest_same = ContentItem.objects.create(content_id=10, content_type="thread", title="Dest Same", scope=scope_a)
        host_same = ContentItem.objects.create(content_id=11, content_type="thread", title="Host Same", scope=scope_a_host)
        host_cross = ContentItem.objects.create(content_id=12, content_type="thread", title="Host Cross", scope=scope_b)
        host_unassigned = ContentItem.objects.create(content_id=13, content_type="thread", title="Host Loose", scope=scope_unassigned)
        post_same = Post.objects.create(content_item=host_same, raw_bbcode="same", clean_text="same")
        post_cross = Post.objects.create(content_item=host_cross, raw_bbcode="cross", clean_text="cross")
        post_unassigned = Post.objects.create(content_item=host_unassigned, raw_bbcode="loose", clean_text="loose")

        sentence_same = Sentence.objects.create(
            content_item=host_same,
            post=post_same,
            text="Sentence same",
            position=0,
            char_count=12,
            start_char=0,
            end_char=12,
            word_position=1,
        )
        sentence_cross = Sentence.objects.create(
            content_item=host_cross,
            post=post_cross,
            text="Sentence cross",
            position=0,
            char_count=14,
            start_char=0,
            end_char=14,
            word_position=1,
        )
        sentence_unassigned = Sentence.objects.create(
            content_item=host_unassigned,
            post=post_unassigned,
            text="Sentence loose",
            position=0,
            char_count=14,
            start_char=0,
            end_char=14,
            word_position=1,
        )

        Suggestion.objects.create(
            destination=dest_same,
            destination_title=dest_same.title,
            host=host_same,
            host_sentence=sentence_same,
            host_sentence_text=sentence_same.text,
            anchor_phrase="same",
            status="pending",
        )
        Suggestion.objects.create(
            destination=dest_same,
            destination_title=dest_same.title,
            host=host_cross,
            host_sentence=sentence_cross,
            host_sentence_text=sentence_cross.text,
            anchor_phrase="cross",
            status="pending",
        )
        Suggestion.objects.create(
            destination=dest_same,
            destination_title=dest_same.title,
            host=host_unassigned,
            host_sentence=sentence_unassigned,
            host_sentence_text=sentence_unassigned.text,
            anchor_phrase="loose",
            status="pending",
        )

    def test_same_silo_filter_returns_only_same_silo_suggestions(self):
        response = self.client.get("/api/suggestions/?same_silo=true")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        suggestion = payload["results"][0]
        self.assertTrue(suggestion["same_silo"])
        self.assertEqual(suggestion["destination_silo_group_name"], "Silo A")
        self.assertEqual(suggestion["host_silo_group_name"], "Silo A")
