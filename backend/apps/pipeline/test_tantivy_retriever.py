"""Tests for TantivyBM25Retriever — in-process BM25 keyword retrieval.

Pure ``SimpleTestCase``: the retriever builds its index in RAM from the
records on the context, so no database, network, or disk is touched.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from django.test import SimpleTestCase


def _record(title: str, scope_title: str = ""):
    return SimpleNamespace(title=title, scope_title=scope_title)


def _context(destination_keys, content_records, content_to_sentence_ids, top_k=5):
    from apps.pipeline.services.candidate_retrievers import RetrievalContext

    return RetrievalContext(
        destination_keys=tuple(destination_keys),
        dest_embeddings=np.zeros((len(destination_keys), 4), dtype=np.float32),
        content_records=content_records,
        content_to_sentence_ids=content_to_sentence_ids,
        top_k=top_k,
        block_size=64,
    )


class TantivyBM25RetrieverTests(SimpleTestCase):
    def _make(self, *, enabled=True):
        from apps.pipeline.services.candidate_retrievers import TantivyBM25Retriever

        return TantivyBM25Retriever(enabled=enabled)

    def test_disabled_returns_empty(self) -> None:
        ctx = _context(
            [("d1", "thread")],
            {("d1", "thread"): _record("Anything")},
            {},
        )
        self.assertEqual(self._make(enabled=False).retrieve(ctx), {})

    def test_keyword_match_surfaces_matching_host(self) -> None:
        dest = ("d1", "thread")
        match = ("h1", "thread")
        miss = ("h2", "thread")
        ctx = _context(
            [dest],
            {
                dest: _record("Roland JV-1080 patch editing"),
                match: _record("JV-1080 patch librarian tips"),
                miss: _record("Completely unrelated cooking recipes"),
            },
            {match: [11, 12], miss: [99]},
        )
        result = self._make().retrieve(ctx)
        self.assertEqual(result, {dest: [11, 12]})

    def test_rare_term_outranks_common_term(self) -> None:
        # BM25 weighs rare terms higher: the host sharing the rare token
        # ("zephyr") must rank above hosts sharing only the common token
        # ("widget", present in every other host).
        dest = ("d1", "thread")
        rare = ("h1", "thread")
        commons = [(f"h{i}", "thread") for i in range(2, 6)]
        records = {
            dest: _record("zephyr widget overview"),
            rare: _record("zephyr maintenance guide"),
        }
        sentence_ids = {rare: [1]}
        for n, key in enumerate(commons, start=2):
            records[key] = _record("widget catalogue entry")
            sentence_ids[key] = [n * 10]
        ctx = _context([dest], records, sentence_ids)
        result = self._make().retrieve(ctx)
        self.assertIn(dest, result)
        self.assertEqual(result[dest][0], 1)

    def test_destination_is_excluded_from_its_own_results(self) -> None:
        dest = ("d1", "thread")
        ctx = _context(
            [dest],
            {dest: _record("Self matching title")},
            {dest: [7]},
        )
        self.assertEqual(self._make().retrieve(ctx), {})

    def test_empty_titles_are_safe(self) -> None:
        dest = ("d1", "thread")
        ctx = _context(
            [dest],
            {dest: _record(""), ("h1", "thread"): _record("")},
            {},
        )
        self.assertEqual(self._make().retrieve(ctx), {})

    def test_query_syntax_characters_do_not_crash(self) -> None:
        # Titles with quotes / colons / parens must not break the query
        # parser — they are stripped before parsing.
        dest = ("d1", "thread")
        host = ("h1", "thread")
        ctx = _context(
            [dest],
            {
                dest: _record('AND OR "NOT" (JV-1080: a^b ~test)'),
                host: _record("JV-1080 test notes"),
            },
            {host: [3]},
        )
        result = self._make().retrieve(ctx)
        self.assertEqual(result, {dest: [3]})
