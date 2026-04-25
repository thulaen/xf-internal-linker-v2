"""Integration test for pick #25 — Callan 1994 passage segmentation wiring.

Proof point: every imported ContentItem with a non-trivial body has
``passages`` populated by ``segment_from_sentences`` from the **same**
sentence list used to produce ``Sentence`` rows. The wiring is
additive (the JSONField defaults to ``[]``) and never blocks an
import on a helper failure.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.content.models import ContentItem, ScopeItem
from apps.pipeline.tasks_import_helpers import _persist_content_body


class PassageSegmentationImportWiringTests(TestCase):
    def setUp(self) -> None:
        self.scope = ScopeItem.objects.create(
            scope_id=88,
            scope_type="node",
            title="passages-test",
        )
        self.content_item = ContentItem.objects.create(
            content_id=30_000,
            content_type="thread",
            title="Passage segmentation fixture",
            scope=self.scope,
        )

    def _long_body(self) -> str:
        """Multi-sentence body big enough to exercise multi-passage output."""
        sentences = []
        for i in range(40):
            sentences.append(
                f"This is sentence number {i} with several alpha bravo "
                f"charlie delta echo foxtrot golf hotel india juliet "
                f"tokens used to push the running token count above the "
                f"default passage window threshold."
            )
        return " ".join(sentences)

    def test_passages_populated_on_long_body(self) -> None:
        """Multi-sentence body → multi-entry ``passages`` list with stable shape."""
        body = self._long_body()

        _persist_content_body(
            content_item=self.content_item,
            raw_body=body,
            clean_text=body,
            new_hash="hash_passages_long",
            first_post_id=None,
        )

        self.content_item.refresh_from_db()
        passages = self.content_item.passages
        self.assertIsInstance(passages, list)
        # Long body yields multiple passages.
        self.assertGreaterEqual(len(passages), 2)
        # Each entry has the expected shape.
        for entry in passages:
            for key in ("index", "text", "token_count", "token_start", "token_end"):
                self.assertIn(key, entry)
            self.assertGreaterEqual(entry["token_count"], 1)
            # token_end must be strictly greater than token_start.
            self.assertGreater(entry["token_end"], entry["token_start"])
        # Indices are 0-based and contiguous.
        indices = [e["index"] for e in passages]
        self.assertEqual(indices, list(range(len(passages))))

    def test_short_body_yields_single_passage(self) -> None:
        """A short body → exactly one passage covering the whole text."""
        body = (
            "Short body that fits inside the default passage window. "
            "Even with a couple of extra sentences it stays under "
            "the 150-token target."
        )

        _persist_content_body(
            content_item=self.content_item,
            raw_body=body,
            clean_text=body,
            new_hash="hash_passages_short",
            first_post_id=None,
        )

        self.content_item.refresh_from_db()
        passages = self.content_item.passages
        # Cardinality depends on sentence-splitting + window math, but
        # a short body is always a single passage in practice.
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["index"], 0)

    def test_empty_body_yields_empty_passages(self) -> None:
        """Cold-start / empty body persists ``[]`` without raising."""
        _persist_content_body(
            content_item=self.content_item,
            raw_body="",
            clean_text="",
            new_hash="hash_passages_empty",
            first_post_id=None,
        )

        self.content_item.refresh_from_db()
        self.assertEqual(self.content_item.passages, [])

    def test_segment_failure_does_not_block_import(self) -> None:
        """A passage-helper exception is logged, not raised — import succeeds."""
        body = "A short body."

        with patch(
            "apps.sources.passages.segment_from_sentences",
            side_effect=RuntimeError("simulated passage failure"),
        ):
            _persist_content_body(
                content_item=self.content_item,
                raw_body=body,
                clean_text=body,
                new_hash="hash_passages_failure",
                first_post_id=None,
            )

        # Import row still saved despite the helper hiccup.
        self.content_item.refresh_from_db()
        self.assertEqual(self.content_item.content_hash, "hash_passages_failure")
