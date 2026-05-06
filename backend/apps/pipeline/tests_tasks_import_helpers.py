"""Tests for the pure-function helpers extracted from ``tasks_import_helpers.py``.

Covers the new private helpers added when shrinking 5 oversized functions
(``_persist_content_body``, ``_upsert_content_item``, ``_fetch_thread_full_body``,
``_parse_xf_item``, ``handle_resource_updates``).

All tests run in ``SimpleTestCase`` (no DB, no Docker) via mocks or tiny
in-memory data structures. DB-touching helpers (Sentence/Token/Post/ContentItem
persistence) get integration coverage from the existing ``test_import_*.py``
suites and are not duplicated here.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.pipeline.tasks_import_helpers import (
    _ParsedItem,
    _absorb_posts_dedup,
    _apply_cross_source_dedup,
    _build_token_objs,
    _bump_content_version,
    _emit_resource_updates_failure,
    _emit_thread_body_failure,
    _extract_xf_fields,
    _fetch_and_absorb_page,
    _fetch_thread_full_body,
    _mark_bloom_filter_safe,
    _maybe_fetch_thread_body,
    _set_nlp_enrichment_safe,
    _set_passages_safe,
    _set_quotation_density_safe,
    _set_salient_entities_safe,
)


# ---------------------------------------------------------------------------
# _bump_content_version
# ---------------------------------------------------------------------------


class BumpContentVersionTests(SimpleTestCase):
    """Verify the four versioning fields are reset/bumped together."""

    def test_increments_version_and_resets_embedding_state(self):
        ci = SimpleNamespace(
            content_hash="OLD",
            content_version=3,
            embedding_model_version="v3",
            embedding_text_hash="abc",
        )
        _bump_content_version(ci, "NEW")
        self.assertEqual(ci.content_hash, "NEW")
        self.assertEqual(ci.content_version, 4)
        self.assertEqual(ci.embedding_model_version, "")
        self.assertEqual(ci.embedding_text_hash, "")

    def test_handles_zero_version(self):
        ci = SimpleNamespace(
            content_hash="",
            content_version=0,
            embedding_model_version="",
            embedding_text_hash="",
        )
        _bump_content_version(ci, "H1")
        self.assertEqual(ci.content_version, 1)
        self.assertEqual(ci.content_hash, "H1")


# ---------------------------------------------------------------------------
# _set_quotation_density_safe
# ---------------------------------------------------------------------------


class SetQuotationDensitySafeTests(SimpleTestCase):
    """Happy path stores returned density; any exception falls back to 0.0."""

    def test_stores_returned_density(self):
        ci = SimpleNamespace(quotation_density=None, pk=42)
        with patch(
            "apps.pipeline.services.text_cleaner.compute_quotation_density",
            return_value=0.42,
        ):
            _set_quotation_density_safe(ci, "[QUOTE]hi[/QUOTE] body")
        self.assertEqual(ci.quotation_density, 0.42)

    def test_falls_back_to_zero_on_exception(self):
        ci = SimpleNamespace(quotation_density=None, pk=42)
        with patch(
            "apps.pipeline.services.text_cleaner.compute_quotation_density",
            side_effect=ValueError("boom"),
        ):
            _set_quotation_density_safe(ci, "anything")
        self.assertEqual(ci.quotation_density, 0.0)

    def test_falls_back_when_helper_module_missing(self):
        ci = SimpleNamespace(quotation_density=None, pk=42)
        with patch.dict("sys.modules", {"apps.pipeline.services.text_cleaner": None}):
            _set_quotation_density_safe(ci, "anything")
        self.assertEqual(ci.quotation_density, 0.0)


# ---------------------------------------------------------------------------
# _apply_cross_source_dedup
# ---------------------------------------------------------------------------


class ApplyCrossSourceDedupTests(SimpleTestCase):
    """Three branches: canonical found, no canonical (and stale link), no canonical (no link)."""

    def test_links_to_canonical_when_found(self):
        ci = SimpleNamespace(pk=10, duplicate_of_id=None, duplicate_of=None)
        canonical = SimpleNamespace(pk=99)
        with patch(
            "apps.content.identity.find_cross_source_duplicate",
            return_value=canonical,
        ):
            _apply_cross_source_dedup(ci, "HASH")
        self.assertIs(ci.duplicate_of, canonical)

    def test_clears_stale_link_when_no_canonical(self):
        ci = SimpleNamespace(pk=10, duplicate_of_id=99, duplicate_of=object())
        with patch(
            "apps.content.identity.find_cross_source_duplicate",
            return_value=None,
        ):
            _apply_cross_source_dedup(ci, "HASH")
        self.assertIsNone(ci.duplicate_of)

    def test_noop_when_already_linked_to_same_canonical(self):
        ci = SimpleNamespace(pk=10, duplicate_of_id=99)
        canonical = SimpleNamespace(pk=99)
        with patch(
            "apps.content.identity.find_cross_source_duplicate",
            return_value=canonical,
        ):
            _apply_cross_source_dedup(ci, "HASH")
        self.assertFalse(hasattr(ci, "duplicate_of"))

    def test_noop_when_no_canonical_and_no_existing_link(self):
        ci = SimpleNamespace(pk=10, duplicate_of_id=None)
        with patch(
            "apps.content.identity.find_cross_source_duplicate",
            return_value=None,
        ):
            _apply_cross_source_dedup(ci, "HASH")
        self.assertFalse(hasattr(ci, "duplicate_of"))


# ---------------------------------------------------------------------------
# _set_salient_entities_safe
# ---------------------------------------------------------------------------


class SetSalientEntitiesSafeTests(SimpleTestCase):
    """Empty list when doc is None; mapped list on success; unchanged on rank_entities failure."""

    def test_doc_none_yields_empty_list(self):
        ci = SimpleNamespace(salient_entities="placeholder", pk=1, title="t")
        _set_salient_entities_safe(ci, None)
        self.assertEqual(ci.salient_entities, [])

    def test_maps_ranked_entities(self):
        ci = SimpleNamespace(salient_entities=None, pk=1, title="Title")
        ranked = [
            SimpleNamespace(text="A", label="ORG", salience=0.8, mention_count=3),
            SimpleNamespace(text="B", label="PERSON", salience=0.5, mention_count=2),
        ]
        with patch(
            "apps.sources.entity_salience.rank_entities", return_value=ranked
        ) as mock_rank:
            _set_salient_entities_safe(ci, doc=MagicMock())
        mock_rank.assert_called_once()
        self.assertEqual(len(ci.salient_entities), 2)
        self.assertEqual(ci.salient_entities[0]["text"], "A")
        self.assertEqual(ci.salient_entities[0]["salience"], 0.8)

    def test_rank_failure_leaves_attr_unchanged(self):
        ci = SimpleNamespace(salient_entities=["unchanged"], pk=1, title=None)
        with patch(
            "apps.sources.entity_salience.rank_entities",
            side_effect=RuntimeError("nope"),
        ):
            _set_salient_entities_safe(ci, doc=MagicMock())
        self.assertEqual(ci.salient_entities, ["unchanged"])


# ---------------------------------------------------------------------------
# _set_nlp_enrichment_safe
# ---------------------------------------------------------------------------


class SetNlpEnrichmentSafeTests(SimpleTestCase):
    """On success stores 7-key metadata + char_ngram_vector; on failure clears both."""

    def test_stores_enrichment_on_success(self):
        ci = SimpleNamespace(nlp_metadata=None, char_ngram_vector=None, pk=1)
        enriched = SimpleNamespace(
            lemmas=["a"], noun_chunks=["b"], acronyms=["c"],
            lexical_richness=0.5, minhash_sketch=[1, 2], phonetic_keys=["X"],
            summary="short",
        )
        fake_enricher = MagicMock()
        fake_enricher.enrich.return_value = (enriched, [0.1, 0.2], None)
        with patch(
            "apps.pipeline.services.nlp_enrichment.NLPEnricher",
            return_value=fake_enricher,
        ):
            _set_nlp_enrichment_safe(ci, "clean text", doc=None)
        self.assertEqual(ci.nlp_metadata["lemmas"], ["a"])
        self.assertEqual(ci.nlp_metadata["summary"], "short")
        self.assertEqual(ci.char_ngram_vector, [0.1, 0.2])

    def test_failure_clears_metadata_and_vector(self):
        ci = SimpleNamespace(
            nlp_metadata={"old": "data"}, char_ngram_vector=[1], pk=1
        )
        fake_enricher = MagicMock()
        fake_enricher.enrich.side_effect = RuntimeError("boom")
        with patch(
            "apps.pipeline.services.nlp_enrichment.NLPEnricher",
            return_value=fake_enricher,
        ):
            _set_nlp_enrichment_safe(ci, "text", doc=None)
        self.assertEqual(ci.nlp_metadata, {})
        self.assertIsNone(ci.char_ngram_vector)


# ---------------------------------------------------------------------------
# _set_passages_safe
# ---------------------------------------------------------------------------


class SetPassagesSafeTests(SimpleTestCase):
    """On success stores mapped passages; on failure leaves attr untouched."""

    def test_stores_passages_on_success(self):
        ci = SimpleNamespace(passages=None, pk=1)
        records = [
            SimpleNamespace(index=0, text="p1", token_count=10, token_start=0, token_end=10),
            SimpleNamespace(index=1, text="p2", token_count=8, token_start=10, token_end=18),
        ]
        sentence_objs = [SimpleNamespace(text="s1"), SimpleNamespace(text="s2")]
        with patch(
            "apps.sources.passages.segment_from_sentences",
            return_value=records,
        ) as mock_seg:
            _set_passages_safe(ci, sentence_objs)
        mock_seg.assert_called_once_with(["s1", "s2"])
        self.assertEqual(len(ci.passages), 2)
        self.assertEqual(ci.passages[0]["index"], 0)
        self.assertEqual(ci.passages[1]["text"], "p2")

    def test_failure_leaves_attr_unchanged(self):
        ci = SimpleNamespace(passages=["original"], pk=1)
        with patch(
            "apps.sources.passages.segment_from_sentences",
            side_effect=RuntimeError("nope"),
        ):
            _set_passages_safe(ci, [SimpleNamespace(text="s")])
        self.assertEqual(ci.passages, ["original"])


# ---------------------------------------------------------------------------
# _build_token_objs
# ---------------------------------------------------------------------------


class BuildTokenObjsTests(SimpleTestCase):
    """Maps every saved sentence's char range back to spaCy tokens."""

    def test_skips_sentence_when_char_span_returns_none(self):
        sent = SimpleNamespace(start_char=0, end_char=10, pk=1)
        doc = MagicMock()
        doc.char_span.return_value = None
        with patch("apps.content.models.Token") as mock_token:
            tokens = _build_token_objs([sent], doc)
        self.assertEqual(tokens, [])
        mock_token.assert_not_called()

    def test_creates_one_token_per_span_token(self):
        sent = SimpleNamespace(start_char=5, end_char=15, pk=1)
        # Fake spaCy tokens — ints/strings spaCy normally exposes.
        token_a = SimpleNamespace(
            text="hi", lemma_="hi", pos_="INTJ", is_stop=False, idx=5,
        )
        token_b = SimpleNamespace(
            text="there", lemma_="there", pos_="ADV", is_stop=True, idx=8,
        )
        fake_span = [token_a, token_b]
        doc = MagicMock()
        doc.char_span.return_value = fake_span
        with patch(
            "apps.content.models.Token", side_effect=lambda **kw: SimpleNamespace(**kw)
        ):
            tokens = _build_token_objs([sent], doc)
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].text, "hi")
        # idx=5, sent.start_char=5 → start_char=0 in sentence-local coords.
        self.assertEqual(tokens[0].start_char, 0)
        self.assertEqual(tokens[1].lemma, "there")


# ---------------------------------------------------------------------------
# _mark_bloom_filter_safe
# ---------------------------------------------------------------------------


class MarkBloomFilterSafeTests(SimpleTestCase):
    """Calls REGISTRY.mark; swallows + logs on any failure."""

    def test_calls_registry_mark_on_happy_path(self):
        with patch(
            "apps.sources.bloom_filter_registry.REGISTRY"
        ) as mock_registry:
            _mark_bloom_filter_safe(123)
        mock_registry.mark.assert_called_once_with(123)

    def test_swallows_registry_failure(self):
        with patch(
            "apps.sources.bloom_filter_registry.REGISTRY"
        ) as mock_registry:
            mock_registry.mark.side_effect = RuntimeError("snapshot missing")
            _mark_bloom_filter_safe(123)


# ---------------------------------------------------------------------------
# _absorb_posts_dedup + _fetch_and_absorb_page
# ---------------------------------------------------------------------------


class AbsorbPostsDedupTests(SimpleTestCase):
    """Adds new post messages, dedups by post_id, skips posts with no id."""

    def test_appends_new_posts(self):
        seen: set[int] = set()
        messages: list[str] = []
        _absorb_posts_dedup(
            [{"post_id": 1, "message": "a"}, {"post_id": 2, "message": "b"}],
            seen, messages,
        )
        self.assertEqual(messages, ["a", "b"])
        self.assertEqual(seen, {1, 2})

    def test_skips_already_seen(self):
        seen = {1}
        messages: list[str] = []
        _absorb_posts_dedup(
            [{"post_id": 1, "message": "dup"}, {"post_id": 2, "message": "new"}],
            seen, messages,
        )
        self.assertEqual(messages, ["new"])
        self.assertEqual(seen, {1, 2})

    def test_skips_missing_post_id(self):
        seen: set[int] = set()
        messages: list[str] = []
        _absorb_posts_dedup(
            [{"message": "no id"}, {"post_id": None, "message": "null id"}],
            seen, messages,
        )
        self.assertEqual(messages, [])
        self.assertEqual(seen, set())


class FetchAndAbsorbPageTests(SimpleTestCase):
    """Calls xf_client.get_posts(thread_id, page=...) and absorbs results."""

    def test_fetches_and_appends(self):
        seen: set[int] = set()
        messages: list[str] = []
        client = MagicMock()
        client.get_posts.return_value = {
            "posts": [{"post_id": 7, "message": "m7"}]
        }
        _fetch_and_absorb_page(client, thread_id=99, page_num=2,
                               seen_post_ids=seen, messages=messages)
        client.get_posts.assert_called_once_with(99, page=2)
        self.assertEqual(messages, ["m7"])
        self.assertEqual(seen, {7})


# ---------------------------------------------------------------------------
# _emit_thread_body_failure
# ---------------------------------------------------------------------------


class EmitThreadBodyFailureTests(SimpleTestCase):
    """Emits the structured event with the expected kwargs."""

    def test_emits_with_event_name_and_severity(self):
        with patch("apps.pipeline.tasks_import_helpers.emit") as mock_emit:
            _emit_thread_body_failure(thread_id=42, exc=ValueError("x"), msg="failed")
        mock_emit.assert_called_once()
        args, kwargs = mock_emit.call_args
        self.assertEqual(args[0], "import.thread_body_failed")
        self.assertEqual(args[1], "failed")
        self.assertEqual(kwargs["severity"], "error")
        self.assertEqual(kwargs["related_entity_type"], "thread")
        self.assertEqual(kwargs["related_entity_id"], "42")
        self.assertEqual(kwargs["runtime_context"], {"error": "x"})


# ---------------------------------------------------------------------------
# _fetch_thread_full_body — orchestration smoke test (helpers tested above)
# ---------------------------------------------------------------------------


class FetchThreadFullBodyTests(SimpleTestCase):
    """Verify the head-only path stitches deduped messages without re-fetching page 1."""

    def test_zero_thread_id_returns_empty(self):
        self.assertEqual(_fetch_thread_full_body(MagicMock(), 0), "")

    def test_empty_first_page_returns_empty(self):
        client = MagicMock()
        client.get_posts.return_value = {"pagination": {"last_page": 1}, "posts": []}
        self.assertEqual(_fetch_thread_full_body(client, 5), "")

    def test_single_page_returns_joined_messages(self):
        client = MagicMock()
        client.get_posts.return_value = {
            "pagination": {"last_page": 1},
            "posts": [
                {"post_id": 1, "message": "A"},
                {"post_id": 2, "message": "B"},
            ],
        }
        result = _fetch_thread_full_body(client, 5)
        self.assertEqual(result, "A\n\nB")
        # Should not refetch page 1.
        client.get_posts.assert_called_once_with(5, page=1)

    def test_failure_returns_empty_and_emits(self):
        client = MagicMock()
        client.get_posts.side_effect = RuntimeError("api down")
        with patch("apps.pipeline.tasks_import_helpers.emit") as mock_emit:
            result = _fetch_thread_full_body(client, 5)
        self.assertEqual(result, "")
        mock_emit.assert_called_once()
        self.assertEqual(mock_emit.call_args[0][0], "import.thread_body_failed")


# ---------------------------------------------------------------------------
# _extract_xf_fields
# ---------------------------------------------------------------------------


class ExtractXfFieldsTests(SimpleTestCase):
    """Pure metadata extraction — thread vs resource, fallback chain, integer coercion."""

    def test_thread_uses_thread_id(self):
        fields = _extract_xf_fields(
            {"thread_id": 7, "resource_id": 99, "title": "T"}, "thread"
        )
        self.assertEqual(fields["c_id"], 7)

    def test_resource_uses_resource_id(self):
        fields = _extract_xf_fields(
            {"thread_id": 7, "resource_id": 99, "title": "T"}, "resource"
        )
        self.assertEqual(fields["c_id"], 99)

    def test_falls_back_to_content_id(self):
        fields = _extract_xf_fields({"content_id": 42, "title": "T"}, "thread")
        self.assertEqual(fields["c_id"], 42)

    def test_body_fallback_chain_picks_first_non_empty(self):
        fields = _extract_xf_fields(
            {"message": "", "post_body": "", "description": "DESC", "title": "T"},
            "resource",
        )
        self.assertEqual(fields["raw_body"], "DESC")

    def test_coerces_counts_to_int_when_strings(self):
        fields = _extract_xf_fields(
            {"view_count": "5", "reply_count": "3", "download_count": "7", "title": "T"},
            "thread",
        )
        self.assertEqual(fields["view_count"], 5)
        self.assertEqual(fields["reply_count"], 3)
        self.assertEqual(fields["download_count"], 7)

    def test_zero_counts_when_missing(self):
        fields = _extract_xf_fields({"title": "T"}, "thread")
        self.assertEqual(fields["view_count"], 0)
        self.assertEqual(fields["reply_count"], 0)
        self.assertEqual(fields["download_count"], 0)

    def test_view_url_falls_back_to_url(self):
        fields = _extract_xf_fields(
            {"url": "https://example.com/x", "title": "T"}, "thread"
        )
        self.assertEqual(fields["view_url"], "https://example.com/x")


# ---------------------------------------------------------------------------
# _maybe_fetch_thread_body
# ---------------------------------------------------------------------------


class MaybeFetchThreadBodyTests(SimpleTestCase):
    """Lazily init xf_client and fetch full body only for full-mode-API-thread items."""

    def test_short_circuits_when_raw_body_present(self):
        state = SimpleNamespace(mode="full", source="api")
        result, client = _maybe_fetch_thread_body(
            state, "thread", "existing body", 1, None
        )
        self.assertEqual(result, "existing body")
        self.assertIsNone(client)

    def test_short_circuits_when_not_full_mode(self):
        state = SimpleNamespace(mode="incremental", source="api")
        result, client = _maybe_fetch_thread_body(state, "thread", "", 1, None)
        self.assertEqual(result, "")

    def test_short_circuits_when_not_thread(self):
        state = SimpleNamespace(mode="full", source="api")
        result, _ = _maybe_fetch_thread_body(state, "resource", "", 1, None)
        self.assertEqual(result, "")

    def test_short_circuits_when_not_api_source(self):
        state = SimpleNamespace(mode="full", source="export")
        result, _ = _maybe_fetch_thread_body(state, "thread", "", 1, None)
        self.assertEqual(result, "")

    def test_initialises_client_and_fetches_when_eligible(self):
        state = SimpleNamespace(mode="full", source="api")
        fake_client_class = MagicMock()
        fake_client_instance = MagicMock()
        fake_client_class.return_value = fake_client_instance
        with patch(
            "apps.sync.services.xenforo_api.XenForoAPIClient", fake_client_class
        ), patch(
            "apps.pipeline.tasks_import_helpers._fetch_thread_full_body",
            return_value="FETCHED",
        ) as mock_fetch:
            body, client = _maybe_fetch_thread_body(state, "thread", "", 99, None)
        fake_client_class.assert_called_once_with()
        mock_fetch.assert_called_once_with(fake_client_instance, 99)
        self.assertEqual(body, "FETCHED")
        self.assertIs(client, fake_client_instance)

    def test_reuses_supplied_client(self):
        state = SimpleNamespace(mode="full", source="api")
        existing = MagicMock()
        with patch(
            "apps.pipeline.tasks_import_helpers._fetch_thread_full_body",
            return_value="X",
        ) as mock_fetch:
            body, client = _maybe_fetch_thread_body(state, "thread", "", 99, existing)
        mock_fetch.assert_called_once_with(existing, 99)
        self.assertIs(client, existing)
        self.assertEqual(body, "X")


# ---------------------------------------------------------------------------
# _build_update_sentences (Sentence is mocked — DB-free pure check)
# ---------------------------------------------------------------------------


class BuildUpdateSentencesTests(SimpleTestCase):
    """Verifies clean-bbcode + split + position increment + word_position derivation."""

    def test_returns_empty_for_empty_clean_text(self):
        # Patch the heavy imports the helper does at call time.
        with patch(
            "apps.pipeline.services.text_cleaner.clean_bbcode", return_value=""
        ), patch(
            "apps.pipeline.services.sentence_splitter.split_sentence_spans",
            return_value=[],
        ), patch("apps.content.models.Sentence", side_effect=lambda **kw: SimpleNamespace(**kw)):
            from apps.pipeline.tasks_import_helpers import _build_update_sentences

            sentences, max_pos = _build_update_sentences(
                content_item=SimpleNamespace(),
                post=SimpleNamespace(word_count=10),
                update_body="[B][/B]",
                base_position=4,
            )
        self.assertEqual(sentences, [])
        self.assertEqual(max_pos, 4)

    def test_increments_position_per_sentence(self):
        spans = [
            SimpleNamespace(text="s1", start_char=0, end_char=2, position=None),
            SimpleNamespace(text="s2", start_char=3, end_char=5, position=None),
        ]
        with patch(
            "apps.pipeline.services.text_cleaner.clean_bbcode", return_value="cleaned"
        ), patch(
            "apps.pipeline.services.sentence_splitter.split_sentence_spans",
            return_value=spans,
        ), patch("apps.content.models.Sentence", side_effect=lambda **kw: SimpleNamespace(**kw)):
            from apps.pipeline.tasks_import_helpers import _build_update_sentences

            sentences, max_pos = _build_update_sentences(
                content_item=SimpleNamespace(),
                post=SimpleNamespace(word_count=12),
                update_body="anything",
                base_position=10,
            )
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0].position, 11)
        self.assertEqual(sentences[1].position, 12)
        self.assertEqual(max_pos, 12)
        # word_position derives from post.word_count + 1.
        self.assertEqual(sentences[0].word_position, 13)


# ---------------------------------------------------------------------------
# _emit_resource_updates_failure
# ---------------------------------------------------------------------------


class EmitResourceUpdatesFailureTests(SimpleTestCase):
    """Emits the structured warning with the expected kwargs."""

    def test_emits_with_warning_severity(self):
        with patch("apps.pipeline.tasks_import_helpers.emit") as mock_emit:
            _emit_resource_updates_failure(
                {"resource_id": 88}, RuntimeError("timeout"), "msg"
            )
        mock_emit.assert_called_once()
        args, kwargs = mock_emit.call_args
        self.assertEqual(args[0], "import.resource_updates_failed")
        self.assertEqual(args[1], "msg")
        self.assertEqual(kwargs["severity"], "warning")
        self.assertEqual(kwargs["related_entity_type"], "resource")
        self.assertEqual(kwargs["related_entity_id"], "88")
        self.assertIn("timeout", kwargs["runtime_context"]["error"])


# ---------------------------------------------------------------------------
# _ParsedItem — sanity check the NamedTuple still constructs
# ---------------------------------------------------------------------------


class ParsedItemSanityTests(SimpleTestCase):
    """Trivial smoke test that the public NamedTuple shape is unchanged."""

    def test_constructs_with_all_fields(self):
        p = _ParsedItem(
            c_id=1, first_post_id=2, title="t", view_url="u", raw_body="b",
            view_count=0, reply_count=0, download_count=0,
            post_date=None, last_post_date=None,
        )
        self.assertEqual(p.c_id, 1)
        self.assertEqual(p.title, "t")
