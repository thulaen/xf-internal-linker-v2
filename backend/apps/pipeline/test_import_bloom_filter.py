"""Integration test for pick #4 — Bloom Filter wiring into the import pipeline.

Proof point: every ``_upsert_content_item`` call in the importer
marks the resulting ``ContentItem.pk`` in the Bloom-filter registry,
so subsequent in-process ``is_known(pk)`` queries return True
without waiting for the next weekly rebuild.

We don't need to exercise the full importer harness — the helper
takes a ``_ParsedItem`` and a scope, both of which we can construct
directly. Then we assert against ``BLOOM_REGISTRY.is_known(...)``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from django.test import TestCase

from apps.content.models import ContentItem, ScopeItem
from apps.pipeline.tasks_import_helpers import _ParsedItem, _upsert_content_item
from apps.sources.bloom_filter_registry import (
    BloomFilterRegistry,
    REGISTRY as BLOOM_REGISTRY,
)


class BloomFilterImportWiringTests(TestCase):
    def setUp(self) -> None:
        # Reset the in-memory filter so test order doesn't matter.
        # We replace the singleton's internal state rather than the
        # singleton itself so importers picking it up via
        # ``from ... import REGISTRY`` see the reset.
        BLOOM_REGISTRY._filter = None
        BLOOM_REGISTRY._loaded = False

        self.scope = ScopeItem.objects.create(
            scope_id=42,
            scope_type="node",
            title="test-scope",
        )

    def _build_parsed(self, *, c_id: int, title: str = "T") -> _ParsedItem:
        """Build a minimal ``_ParsedItem`` payload."""
        now = datetime.now(timezone.utc)
        return _ParsedItem(
            c_id=c_id,
            first_post_id=c_id * 10,
            title=title,
            view_url=f"https://example.com/threads/{title}.{c_id}/",
            raw_body="<p>body</p>",
            view_count=1,
            reply_count=0,
            download_count=0,
            post_date=now,
            last_post_date=now,
        )

    def test_upsert_marks_pk_in_bloom_registry(self) -> None:
        """A newly imported ContentItem's pk should be queryable via the Bloom filter."""
        parsed = self._build_parsed(c_id=1001)

        item = _upsert_content_item(parsed, c_type="thread", current_scope=self.scope)

        self.assertIsInstance(item, ContentItem)
        self.assertTrue(
            BLOOM_REGISTRY.is_known(item.pk),
            f"Bloom registry should report pk={item.pk} as known after import",
        )

    def test_unrelated_pk_not_known(self) -> None:
        """The Bloom filter should not falsely claim never-imported pks are known."""
        # Note: Bloom filters can have false positives but never false
        # negatives. With only one mark in scope, ``is_known`` of an
        # unrelated PK on a fresh-but-non-empty filter is overwhelmingly
        # likely to return False (FPR ≈ 1% by default on 10M-cap), so
        # this test is reliable.
        parsed = self._build_parsed(c_id=2002)
        item = _upsert_content_item(parsed, c_type="thread", current_scope=self.scope)

        # A pk we never marked.
        random_other_pk = item.pk + 999_999
        self.assertFalse(BLOOM_REGISTRY.is_known(random_other_pk))

    def test_repeated_upsert_idempotent_in_filter(self) -> None:
        """Re-importing the same content_id keeps it marked (no flapping)."""
        parsed = self._build_parsed(c_id=3003)
        item_first = _upsert_content_item(
            parsed, c_type="thread", current_scope=self.scope
        )
        item_second = _upsert_content_item(
            parsed, c_type="thread", current_scope=self.scope
        )

        # Same row was upserted, not a fresh insert.
        self.assertEqual(item_first.pk, item_second.pk)
        # Filter still reports it as known.
        self.assertTrue(BLOOM_REGISTRY.is_known(item_first.pk))

    def test_mark_failure_does_not_block_import(self) -> None:
        """A Bloom-registry exception is swallowed — the import row still saves."""
        from unittest.mock import patch

        parsed = self._build_parsed(c_id=4004)

        with patch.object(
            BLOOM_REGISTRY,
            "mark",
            side_effect=RuntimeError("simulated registry failure"),
        ):
            item = _upsert_content_item(
                parsed, c_type="thread", current_scope=self.scope
            )

        # The row was saved despite the registry hiccup — Bloom is an
        # optimisation, not a hard dependency.
        self.assertIsInstance(item, ContentItem)
        self.assertEqual(item.content_id, 4004)


class BloomRegistryIsolationTests(TestCase):
    """Verify the registry's ``is_known`` cold-start path is safe."""

    def test_fresh_registry_returns_false_on_unknown_pk(self) -> None:
        """A registry with no snapshot must say 'not known' (safe direction)."""
        fresh = BloomFilterRegistry()
        self.assertFalse(fresh.is_known(123))

    def test_marked_pk_is_known_after_mark(self) -> None:
        """Calling ``mark`` on a fresh registry creates the filter and tracks the pk."""
        fresh = BloomFilterRegistry()
        fresh.mark(456)
        self.assertTrue(fresh.is_known(456))
