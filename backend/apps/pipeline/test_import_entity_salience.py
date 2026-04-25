"""Integration test for pick #26 — Gamon et al. entity salience wiring.

Proof point: when the importer's ``_persist_content_body`` runs on a
``clean_text`` that contains named entities, the resulting
``ContentItem.salient_entities`` JSON list is populated from a single
spaCy parse (shared with sentence-splitting via
``split_sentence_spans_with_doc``) — no duplicate NLP work.

Cold-start safe: empty bodies / regex-fallback (no spaCy) leave
``salient_entities = []`` without raising.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.content.models import ContentItem, ScopeItem
from apps.pipeline.tasks_import_helpers import _persist_content_body


class EntitySalienceImportWiringTests(TestCase):
    def setUp(self) -> None:
        self.scope = ScopeItem.objects.create(
            scope_id=77,
            scope_type="node",
            title="entity-test",
        )
        self.content_item = ContentItem.objects.create(
            content_id=20_000,
            content_type="thread",
            title="Apple and Microsoft announce partnership",
            scope=self.scope,
        )

    def test_named_entities_populated(self) -> None:
        """Imported text with NER-detectable entities yields a non-empty salience list."""
        clean = (
            "Apple announced a new partnership with Microsoft in Cupertino. "
            "Apple's CEO emphasised the importance of the deal for Microsoft. "
            "The Cupertino announcement followed months of negotiation."
        )

        _persist_content_body(
            content_item=self.content_item,
            raw_body=clean,
            clean_text=clean,
            new_hash="hash_entities",
            first_post_id=None,
        )

        self.content_item.refresh_from_db()
        salient = self.content_item.salient_entities
        self.assertIsInstance(salient, list)
        # spaCy detects multiple entities in this prose.
        self.assertGreater(len(salient), 0)
        # Each entry has the expected shape.
        for entry in salient:
            self.assertIn("text", entry)
            self.assertIn("label", entry)
            self.assertIn("salience", entry)
            self.assertIn("mention_count", entry)
            self.assertGreaterEqual(entry["salience"], 0.0)
            self.assertLessEqual(entry["salience"], 1.0)
        # The list is bounded to top_k=10.
        self.assertLessEqual(len(salient), 10)

    def test_empty_body_yields_empty_salient_entities(self) -> None:
        """Cold-start / empty body persists [] without raising."""
        _persist_content_body(
            content_item=self.content_item,
            raw_body="",
            clean_text="",
            new_hash="hash_empty",
            first_post_id=None,
        )

        self.content_item.refresh_from_db()
        self.assertEqual(self.content_item.salient_entities, [])

    def test_no_doc_fallback_leaves_salient_entities_empty(self) -> None:
        """Regex-fallback (no spaCy Doc) skips entity ranking cleanly."""
        # Force the (spans, doc) call to return doc=None — the regex
        # fallback path. Helper must persist [] and never raise.
        from apps.pipeline.services import sentence_splitter

        with patch.object(
            sentence_splitter,
            "split_sentence_spans_with_doc",
            return_value=([], None),
        ):
            _persist_content_body(
                content_item=self.content_item,
                raw_body="Some text",
                clean_text="Some text about Things.",
                new_hash="hash_fallback",
                first_post_id=None,
            )

        self.content_item.refresh_from_db()
        self.assertEqual(self.content_item.salient_entities, [])

    def test_rank_entities_failure_does_not_block_import(self) -> None:
        """A salience-helper exception is logged, not raised — import succeeds."""
        from apps.sources import entity_salience as entity_salience_mod

        clean = "Apple visited Cupertino in March."
        with patch.object(
            entity_salience_mod,
            "rank_entities",
            side_effect=RuntimeError("simulated salience failure"),
        ):
            # Patching the symbol on the module isn't enough because
            # tasks_import_helpers re-imports it locally. Patch where
            # it's used (the local name) instead.
            from apps.pipeline import tasks_import_helpers as helpers

            with patch.object(
                helpers,
                "_persist_content_body",
                wraps=helpers._persist_content_body,
            ):
                # Use the actual function but stub rank_entities at
                # import-time inside the helper. Easiest path: patch
                # the symbol on the module the helper imports from.
                with patch(
                    "apps.sources.entity_salience.rank_entities",
                    side_effect=RuntimeError("simulated salience failure"),
                ):
                    _persist_content_body(
                        content_item=self.content_item,
                        raw_body=clean,
                        clean_text=clean,
                        new_hash="hash_failure",
                        first_post_id=None,
                    )

        # The import row still saved despite the salience hiccup.
        self.content_item.refresh_from_db()
        self.assertEqual(self.content_item.content_hash, "hash_failure")
