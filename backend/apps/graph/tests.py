from django.test import TestCase, override_settings

from apps.content.models import ContentItem, Post, ScopeItem
from apps.graph.models import ExistingLink
from apps.graph.services.graph_sync import refresh_existing_links


@override_settings(
    XENFORO_BASE_URL="https://forum.example.com",
    WORDPRESS_BASE_URL="https://blog.example.com",
)
class CrossSourceExistingLinkTests(TestCase):
    def test_refresh_existing_links_resolves_xf_to_wp_and_wp_to_xf_edges(self):
        xf_scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        wp_scope = ScopeItem.objects.create(scope_id=1, scope_type="wp_posts", title="WordPress Posts")

        xf_item = ContentItem.objects.create(
            content_id=101,
            content_type="thread",
            title="Forum Thread",
            scope=xf_scope,
            url="https://forum.example.com/threads/forum-thread.101",
        )
        wp_item = ContentItem.objects.create(
            content_id=202,
            content_type="wp_post",
            title="Blog Post",
            scope=wp_scope,
            url="https://blog.example.com/blog-post",
        )

        Post.objects.create(
            content_item=xf_item,
            raw_bbcode="[URL=https://blog.example.com/blog-post]Blog Post[/URL]",
            clean_text="Blog Post",
        )
        Post.objects.create(
            content_item=wp_item,
            raw_bbcode='<p><a href="https://forum.example.com/threads/forum-thread.101">Forum Thread</a></p>',
            clean_text="Forum Thread",
        )

        refreshed = refresh_existing_links()

        self.assertEqual(refreshed, 2)
        self.assertTrue(ExistingLink.objects.filter(from_content_item=xf_item, to_content_item=wp_item).exists())
        self.assertTrue(ExistingLink.objects.filter(from_content_item=wp_item, to_content_item=xf_item).exists())
