from django.test import TestCase, override_settings

from apps.content.models import ContentItem, Post, ScopeItem
from apps.graph.models import ExistingLink
from apps.graph.services.graph_sync import refresh_existing_links, sync_existing_links
from apps.pipeline.services.link_parser import LinkEdge, extract_internal_links


@override_settings(
    XENFORO_BASE_URL="https://forum.example.com",
    WORDPRESS_BASE_URL="https://blog.example.com",
)
class CrossSourceExistingLinkTests(TestCase):
    def test_extract_internal_links_preserves_true_source_order_and_keeps_earliest_duplicate(self):
        wp_scope = ScopeItem.objects.create(scope_id=1, scope_type="wp_posts", title="WordPress Posts")
        ContentItem.objects.create(
            content_id=202,
            content_type="thread",
            title="Second Topic",
            url="https://forum.example.com/threads/second-topic.202",
        )
        ContentItem.objects.create(
            content_id=303,
            content_type="thread",
            title="Third Topic",
            url="https://forum.example.com/threads/third-topic.303",
        )
        ContentItem.objects.create(
            content_id=404,
            content_type="wp_post",
            title="Blog Post",
            scope=wp_scope,
            url="https://blog.example.com/blog-post",
        )

        raw = (
            'Before <a href="https://forum.example.com/threads/second-topic.202">Second topic</a> after. '
            'Words [URL=https://blog.example.com/blog-post]Blog post[/URL] more words. '
            'Start https://forum.example.com/threads/third-topic.303 end. '
            '[URL=https://forum.example.com/threads/second-topic.202]Later duplicate[/URL]'
        )

        edges = extract_internal_links(
            raw,
            from_content_id=101,
            from_content_type="thread",
            forum_domains=["forum.example.com", "blog.example.com"],
        )

        self.assertEqual(
            [(edge.to_content_id, edge.extraction_method) for edge in edges],
            [
                (202, "html_anchor"),
                (404, "bbcode_anchor"),
                (303, "bare_url"),
            ],
        )
        self.assertEqual([edge.link_ordinal for edge in edges], [0, 1, 2])
        self.assertEqual([edge.source_internal_link_count for edge in edges], [3, 3, 3])
        self.assertEqual(edges[0].anchor_text, "Second topic")
        self.assertEqual(edges[0].context_class, "contextual")
        self.assertEqual(edges[1].context_class, "contextual")
        self.assertEqual(edges[2].context_class, "contextual")

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
        xf_to_wp = ExistingLink.objects.get(from_content_item=xf_item, to_content_item=wp_item)
        wp_to_xf = ExistingLink.objects.get(from_content_item=wp_item, to_content_item=xf_item)
        self.assertEqual(xf_to_wp.extraction_method, "bbcode_anchor")
        self.assertEqual(xf_to_wp.link_ordinal, 0)
        self.assertEqual(xf_to_wp.source_internal_link_count, 1)
        self.assertEqual(wp_to_xf.extraction_method, "html_anchor")
        self.assertEqual(wp_to_xf.link_ordinal, 0)
        self.assertEqual(wp_to_xf.source_internal_link_count, 1)

    def test_sync_existing_links_updates_weighted_fields_in_place(self):
        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        source = ContentItem.objects.create(content_id=101, content_type="thread", title="Source", scope=scope)
        destination = ContentItem.objects.create(content_id=202, content_type="thread", title="Destination", scope=scope)
        existing = ExistingLink.objects.create(
            from_content_item=source,
            to_content_item=destination,
            anchor_text="Old anchor",
            extraction_method="html_anchor",
            link_ordinal=0,
            source_internal_link_count=1,
            context_class="contextual",
        )
        original_pk = existing.pk

        active_count = sync_existing_links(
            source,
            [
                LinkEdge(
                    from_content_id=101,
                    from_content_type="thread",
                    to_content_id=202,
                    to_content_type="thread",
                    anchor_text="New anchor",
                    extraction_method="bare_url",
                    link_ordinal=2,
                    source_internal_link_count=4,
                    context_class="weak_context",
                )
            ],
        )

        self.assertEqual(active_count, 1)
        self.assertEqual(ExistingLink.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.pk, original_pk)
        self.assertEqual(existing.anchor_text, "New anchor")
        self.assertEqual(existing.extraction_method, "bare_url")
        self.assertEqual(existing.link_ordinal, 2)
        self.assertEqual(existing.source_internal_link_count, 4)
        self.assertEqual(existing.context_class, "weak_context")
