"""Property tests for existing link detection."""

from django.test import SimpleTestCase
from apps.pipeline.services.link_parser import extract_internal_links, _ResolvedLink, _MatchedLink
from apps.content.models import ContentItem

class ExistingLinkPropertyTests(SimpleTestCase):
    def test_extract_internal_links_rejects_self_link(self):
        # Identical source and destination is rejected (no self-link)
        raw_bbcode = "Check out [URL=https://example.com/threads/1]this[/URL]"
        
        # We need to mock _resolve_target to return the same ID as from_content_id
        import apps.pipeline.services.link_parser as lp
        original_resolve = lp._resolve_target
        try:
            lp._resolve_target = lambda url, domains: (1, "thread")
            
            edges = lp.extract_internal_links(
                raw_bbcode=raw_bbcode,
                from_content_id=1,
                from_content_type="thread",
                forum_domains=["example.com"]
            )
            
            # The self link should be rejected
            self.assertEqual(len(edges), 0)
        finally:
            lp._resolve_target = original_resolve

    def test_deduplication(self):
        # Already-linked destinations are penalised or removed (deduplicated per destination)
        raw_bbcode = "Link [URL=https://example.com/threads/2]one[/URL] and [URL=https://example.com/threads/2]two[/URL]"
        
        import apps.pipeline.services.link_parser as lp
        original_resolve = lp._resolve_target
        try:
            lp._resolve_target = lambda url, domains: (2, "thread")
            
            edges = lp.extract_internal_links(
                raw_bbcode=raw_bbcode,
                from_content_id=1,
                from_content_type="thread",
                forum_domains=["example.com"]
            )
            
            # Should only keep the first one
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0].anchor_text, "one")
        finally:
            lp._resolve_target = original_resolve

    def test_html_and_bbcode(self):
        # Should detect existing links at write time and read time (both bbcode and html tags)
        raw_bbcode = "Link <a href='https://example.com/threads/2'>html</a> and [URL=https://example.com/threads/3]bbcode[/URL]"
        
        import apps.pipeline.services.link_parser as lp
        original_resolve = lp._resolve_target
        try:
            def mock_resolve(url, domains):
                if 'threads/2' in url:
                    return (2, "thread")
                return (3, "thread")
                
            lp._resolve_target = mock_resolve
            
            edges = lp.extract_internal_links(
                raw_bbcode=raw_bbcode,
                from_content_id=1,
                from_content_type="thread",
                forum_domains=["example.com"]
            )
            
            self.assertEqual(len(edges), 2)
            self.assertEqual(edges[0].extraction_method, "html_anchor")
            self.assertEqual(edges[0].anchor_text, "html")
            self.assertEqual(edges[1].extraction_method, "bbcode_anchor")
            self.assertEqual(edges[1].anchor_text, "bbcode")
        finally:
            lp._resolve_target = original_resolve
