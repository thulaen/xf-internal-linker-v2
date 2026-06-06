"""Property tests for broken link detection."""

from django.test import SimpleTestCase
from apps.graph.models import BrokenLink
from apps.pipeline.tasks_broken_links import store_probe_result
from django.utils import timezone
from collections import namedtuple

# A mock for the existing record to test updates without DB
class MockBrokenLink:
    def __init__(self, status):
        self.status = status
        self.http_status = None
        self.redirect_url = None
        self.last_checked_at = None

class BrokenLinkPropertyTests(SimpleTestCase):
    def test_broken_link_creation(self):
        # A new broken link should be created if not existing
        to_create = []
        to_update = []
        checked_at = timezone.now()
        flagged, fixed = store_probe_result(
            source_content_id=1,
            url="http://example.com/broken",
            http_status=404,
            redirect_url="",
            existing_records={},
            to_create=to_create,
            to_update=to_update,
            checked_at=checked_at
        )
        self.assertEqual(flagged, 1)
        self.assertEqual(fixed, 0)
        self.assertEqual(len(to_create), 1)
        self.assertEqual(len(to_update), 0)
        
        bl = to_create[0]
        self.assertEqual(bl.http_status, 404)
        self.assertEqual(bl.status, BrokenLink.STATUS_OPEN)
        self.assertEqual(bl.source_content_id, 1)
        self.assertEqual(bl.url, "http://example.com/broken")

    def test_existing_broken_link_updated(self):
        # An existing broken link should be updated
        existing = MockBrokenLink(status=BrokenLink.STATUS_OPEN)
        to_create = []
        to_update = []
        checked_at = timezone.now()
        
        flagged, fixed = store_probe_result(
            source_content_id=1,
            url="http://example.com/broken",
            http_status=500,
            redirect_url="",
            existing_records={(1, "http://example.com/broken"): existing},
            to_create=to_create,
            to_update=to_update,
            checked_at=checked_at
        )
        
        self.assertEqual(flagged, 1)
        self.assertEqual(fixed, 0)
        self.assertEqual(len(to_create), 0)
        self.assertEqual(len(to_update), 1)
        
        bl = to_update[0]
        self.assertEqual(bl.http_status, 500)
        self.assertEqual(bl.status, BrokenLink.STATUS_OPEN)

    def test_broken_link_fixed(self):
        # An existing broken link that is now OK should be marked FIXED
        existing = MockBrokenLink(status=BrokenLink.STATUS_OPEN)
        to_create = []
        to_update = []
        checked_at = timezone.now()
        
        flagged, fixed = store_probe_result(
            source_content_id=1,
            url="http://example.com/ok",
            http_status=200,
            redirect_url="",
            existing_records={(1, "http://example.com/ok"): existing},
            to_create=to_create,
            to_update=to_update,
            checked_at=checked_at
        )
        
        self.assertEqual(flagged, 0)
        self.assertEqual(fixed, 1)
        self.assertEqual(len(to_create), 0)
        self.assertEqual(len(to_update), 1)
        
        bl = to_update[0]
        self.assertEqual(bl.http_status, 200)
        self.assertEqual(bl.status, BrokenLink.STATUS_FIXED)
        
    def test_ignored_status_preserved(self):
        # If an existing broken link is IGNORED, it should stay IGNORED
        existing = MockBrokenLink(status=BrokenLink.STATUS_IGNORED)
        to_create = []
        to_update = []
        checked_at = timezone.now()
        
        flagged, fixed = store_probe_result(
            source_content_id=1,
            url="http://example.com/broken",
            http_status=404,
            redirect_url="",
            existing_records={(1, "http://example.com/broken"): existing},
            to_create=to_create,
            to_update=to_update,
            checked_at=checked_at
        )
        
        self.assertEqual(flagged, 1)
        self.assertEqual(fixed, 0)
        self.assertEqual(len(to_update), 1)
        self.assertEqual(to_update[0].status, BrokenLink.STATUS_IGNORED)
