from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability import api
from apps.observability.metric_specs import RESERVED_OBSERVABILITY_ITEMS


class ReservedObservabilityCatalogTests(SimpleTestCase):
    def test_catalog_tracks_all_85_reserved_plan_items(self):
        ids = [item.item_id for item in RESERVED_OBSERVABILITY_ITEMS]

        self.assertEqual(len(ids), 85)
        self.assertEqual(ids, list(range(1, 86)))

    def test_metric_catalog_includes_disk_capacity_used_by_alert_rules(self):
        names = set(api.reserved_metric_names())

        self.assertIn("xf_system_disk_usage_bytes", names)
        self.assertIn("xf_system_disk_capacity_bytes", names)


class ReservedInstrumentationTests(SimpleTestCase):
    def test_labeled_counter_observes_imported_posts(self):
        from apps.observability import instruments

        before = api.generate_latest(api.get_registry()).decode("utf-8")

        instruments.observe_import_posts("wordpress", count=5)
        after = api.generate_latest(api.get_registry()).decode("utf-8")

        self.assertIn("xf_import_posts_total", after)
        self.assertNotEqual(before, after)

    def test_cleaning_and_sentence_helpers_emit_reserved_metrics(self):
        from apps.observability import instruments

        instruments.observe_cleaning_result(
            raw_text="This raw document has a [QUOTE]quoted block[/QUOTE].",
            cleaned_text="This raw document has content.",
        )
        instruments.observe_sentence_split(
            total_sentences=3,
            bad_sentences=1,
        )
        body = api.generate_latest(api.get_registry()).decode("utf-8")

        self.assertIn("xf_cleaning_documents_total", body)
        self.assertIn("xf_cleaning_text_length_chars", body)
        self.assertIn("xf_sentence_split_bad_sentence_ratio", body)

    def test_safe_metric_helpers_do_not_crash_callers(self):
        from apps.observability import instruments

        class BrokenMetric:
            def inc(self, amount=1):
                raise RuntimeError("metric backend unavailable")

        instruments.safe_inc(BrokenMetric())

    def test_clean_import_text_emits_cleaning_metrics(self):
        from apps.pipeline.services.text_cleaner import clean_import_text

        before = api.generate_latest(api.get_registry()).decode("utf-8")
        clean_import_text("<article><p>Hello useful page text.</p></article>")
        after = api.generate_latest(api.get_registry()).decode("utf-8")

        self.assertNotEqual(before, after)
        self.assertIn("xf_cleaning_documents_total", after)

    def test_split_sentences_emits_sentence_metrics(self):
        from apps.pipeline.services.sentence_splitter import split_sentences

        before = api.generate_latest(api.get_registry()).decode("utf-8")
        split_sentences(
            "This is a useful first sentence. This is a useful second sentence."
        )
        after = api.generate_latest(api.get_registry()).decode("utf-8")

        self.assertNotEqual(before, after)
        self.assertIn("xf_sentence_split_sentences_per_doc", after)

    def test_faiss_search_emits_search_metrics_even_when_index_is_empty(self):
        import numpy as np

        from apps.pipeline.services import faiss_index

        with faiss_index._index_lock:
            faiss_index._faiss_index = None
            faiss_index._faiss_id_map = []
            faiss_index._faiss_content_type_map = []

        before = api.generate_latest(api.get_registry()).decode("utf-8")
        faiss_index.faiss_search(np.zeros((2, 3), dtype=np.float32), k=5)
        after = api.generate_latest(api.get_registry()).decode("utf-8")

        self.assertNotEqual(before, after)
        self.assertIn("xf_index_search_seconds", after)
