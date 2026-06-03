"""Convention-named SimpleTestCase coverage for apps/observability/helpers.py.

``bucket_url_label`` turns a raw request path into a low-cardinality metric
label by stripping the query string, replacing numeric ids with ``/:id`` and
UUIDs with ``/:uuid``, and clamping the result to 160 characters. Exact string
assertions (not substring) pin every replacement literal and the length cap so
the diff-scoped mutation gate cannot survive a changed constant.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability.helpers import bucket_url_label


class BucketUrlLabelTests(SimpleTestCase):
    def test_empty_path_becomes_root(self) -> None:
        self.assertEqual(bucket_url_label(""), "/")

    def test_none_path_becomes_root(self) -> None:
        self.assertEqual(bucket_url_label(None), "/")

    def test_query_string_is_dropped(self) -> None:
        self.assertEqual(bucket_url_label("/posts?page=2"), "/posts")

    def test_numeric_id_is_bucketed(self) -> None:
        self.assertEqual(bucket_url_label("/posts/42"), "/posts/:id")

    def test_numeric_id_in_middle_is_bucketed(self) -> None:
        self.assertEqual(bucket_url_label("/posts/42/comments"), "/posts/:id/comments")

    def test_uuid_is_bucketed(self) -> None:
        path = "/users/12345678-1234-1234-1234-123456789abc"
        self.assertEqual(bucket_url_label(path), "/users/:uuid")

    def test_label_is_clamped_to_160_chars(self) -> None:
        # assertEqual on the exact length kills the +1 mutation of the [:160]
        # slice (a >= check would still pass on 161).
        long_path = "/" + ("a" * 300)
        self.assertEqual(len(bucket_url_label(long_path)), 160)
