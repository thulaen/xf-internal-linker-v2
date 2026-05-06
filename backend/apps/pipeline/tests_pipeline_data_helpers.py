"""Tests for the pure-function helpers extracted from pipeline/services/pipeline_data.py.

Covers the 14 new private helpers added when shrinking 6 oversized functions.
All tests run in ``SimpleTestCase`` (no DB, no Docker) via mocks or tiny
in-memory data structures.
"""

from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.pipeline.services.pipeline_data import (
    _apply_langid_filter,
    _build_query_cache_if_enabled,
    _build_sentence_record_from_row,
    _build_simple_graph_caches,
    _build_silo_cache_if_enabled,
    _detect_link_farm_if_enabled,
    _empty_pipeline_result,
    _full_corpus_if_scoped,
    _load_keyword_baseline_if_enabled,
    _load_rare_term_profiles,
    _parse_sentence_loader_input,
    _resolve_scope_hierarchy,
    _score_keyword_stuffing_if_enabled,
)


# ---------------------------------------------------------------------------
# _empty_pipeline_result
# ---------------------------------------------------------------------------


class EmptyPipelineResultTests(SimpleTestCase):
    """Verify the zero-result factory produces correctly shaped objects."""

    def test_default_all_zeros(self):
        from apps.pipeline.services.pipeline import PipelineResult

        result = _empty_pipeline_result()
        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.items_in_scope, 0)
        self.assertEqual(result.suggestions_created, 0)
        self.assertEqual(result.destinations_skipped, 0)
        self.assertEqual(result.run_id, "")

    def test_custom_items_in_scope(self):
        result = _empty_pipeline_result(items_in_scope=7, destinations_skipped=7)
        self.assertEqual(result.items_in_scope, 7)
        self.assertEqual(result.destinations_skipped, 7)
        self.assertEqual(result.suggestions_created, 0)


# ---------------------------------------------------------------------------
# _full_corpus_if_scoped
# ---------------------------------------------------------------------------


class FullCorpusIfScopedTests(SimpleTestCase):
    """When no scope filter is active, passthrough; when active, call loader."""

    def test_no_scope_returns_passthrough(self):
        sentinel = {"key": "value"}
        result = _full_corpus_if_scoped(sentinel, None, None, None)
        self.assertIs(result, sentinel)

    def test_any_scope_set_calls_loader(self):
        sentinel = {"key": "value"}
        fake_full = {"a": 1, "b": 2}
        with patch(
            "apps.pipeline.services.pipeline_data._load_content_records",
            return_value=fake_full,
        ) as mock_loader:
            result = _full_corpus_if_scoped(sentinel, {1}, None, None)
        mock_loader.assert_called_once_with()
        self.assertIs(result, fake_full)

    def test_destination_ci_ids_triggers_loader(self):
        with patch(
            "apps.pipeline.services.pipeline_data._load_content_records",
            return_value={},
        ) as mock_loader:
            _full_corpus_if_scoped({}, None, None, {42})
        mock_loader.assert_called_once()


# ---------------------------------------------------------------------------
# _parse_sentence_loader_input
# ---------------------------------------------------------------------------


class ParseSentenceLoaderInputTests(SimpleTestCase):
    """Dict and iterable inputs produce identical content_pks."""

    def test_empty_set_gives_empty_pks(self):
        records, pks = _parse_sentence_loader_input(set())
        self.assertEqual(records, {})
        self.assertEqual(pks, [])

    def test_set_input_content_records_is_empty_dict(self):
        keys = {(1, "post"), (2, "post")}
        records, pks = _parse_sentence_loader_input(keys)
        self.assertEqual(records, {})
        self.assertCountEqual(pks, [1, 2])

    def test_dict_input_returns_same_dict_and_correct_pks(self):
        d = {(10, "post"): "rec_a", (20, "post"): "rec_b"}
        records, pks = _parse_sentence_loader_input(d)
        self.assertIs(records, d)
        self.assertEqual(pks, [10, 20])


# ---------------------------------------------------------------------------
# _build_sentence_record_from_row
# ---------------------------------------------------------------------------


class BuildSentenceRecordFromRowTests(SimpleTestCase):
    """Raw SQL row tuples are mapped to correct SentenceRecord fields."""

    def _make_row(self, sid=1, cid=10, ctype="post", text="hello world",
                  char_count=11, position=0):
        return (sid, cid, ctype, text, char_count, position)

    def test_basic_row_fields(self):
        row = self._make_row()
        content_records = {(10, "post"): MagicMock(nlp_metadata={"k": "v"})}
        ckey, record = _build_sentence_record_from_row(row, content_records)
        self.assertEqual(ckey, (10, "post"))
        self.assertEqual(record.sentence_id, 1)
        self.assertEqual(record.content_id, 10)
        self.assertEqual(record.text, "hello world")
        self.assertEqual(record.nlp_metadata, {"k": "v"})

    def test_missing_nlp_metadata_fallback(self):
        row = self._make_row(cid=99, ctype="page")
        ckey, record = _build_sentence_record_from_row(row, {})
        self.assertEqual(record.nlp_metadata, {})

    def test_zero_char_count_falls_back_to_len_text(self):
        row = self._make_row(text="abc", char_count=0)
        ckey, record = _build_sentence_record_from_row(row, {(10, "post"): MagicMock(nlp_metadata={})})
        self.assertEqual(record.char_count, 3)


# ---------------------------------------------------------------------------
# _resolve_scope_hierarchy
# ---------------------------------------------------------------------------


class ResolveScopeHierarchyTests(SimpleTestCase):
    """Scope chain is walked correctly for all levels of nesting."""

    def _ci(self, scope):
        ci = MagicMock()
        ci.scope = scope
        return ci

    def test_no_scope_returns_four_nones(self):
        ci = self._ci(None)
        scope, parent, grandparent, silo_group = _resolve_scope_hierarchy(ci)
        self.assertIsNone(scope)
        self.assertIsNone(parent)
        self.assertIsNone(grandparent)
        self.assertIsNone(silo_group)

    def test_scope_only_no_parent(self):
        scope = MagicMock()
        scope.parent = None
        scope.silo_group = None
        ci = self._ci(scope)
        s, p, gp, sg = _resolve_scope_hierarchy(ci)
        self.assertIs(s, scope)
        self.assertIsNone(p)
        self.assertIsNone(gp)
        self.assertIsNone(sg)

    def test_full_three_level_hierarchy(self):
        grandparent = MagicMock()
        grandparent.parent = None
        parent = MagicMock()
        parent.parent = grandparent
        silo_group = MagicMock()
        scope = MagicMock()
        scope.parent = parent
        scope.silo_group = silo_group
        ci = self._ci(scope)
        s, p, gp, sg = _resolve_scope_hierarchy(ci)
        self.assertIs(s, scope)
        self.assertIs(p, parent)
        self.assertIs(gp, grandparent)
        self.assertIs(sg, silo_group)


# ---------------------------------------------------------------------------
# _apply_langid_filter
# ---------------------------------------------------------------------------


class ApplyLangidFilterTests(SimpleTestCase):
    """Filter is cold-start safe; progress callback fires only on count change."""

    def test_empty_input_returns_empty(self):
        calls = []
        result = _apply_langid_filter({}, lambda pct, msg: calls.append(pct))
        self.assertEqual(result, {})
        self.assertEqual(calls, [])

    def test_passthrough_when_counts_unchanged(self):
        d = {(1, "post"): MagicMock()}
        calls = []
        with patch(
            "apps.sources.language_filter.filter_english_content_records",
            return_value=d,
        ):
            result = _apply_langid_filter(d, lambda pct, msg: calls.append(pct))
        self.assertIs(result, d)
        self.assertEqual(calls, [], msg="progress_fn must not fire when nothing dropped")


# ---------------------------------------------------------------------------
# _build_simple_graph_caches
# ---------------------------------------------------------------------------


class BuildSimpleGraphCachesTests(SimpleTestCase):
    """All four caches are None when their respective signals are disabled."""

    def _settings(self, kmig=False, tapb=False, kcib=False, berp=False):
        s = MagicMock()
        s.kmig.enabled = kmig
        s.tapb.enabled = tapb
        s.kcib.enabled = kcib
        s.berp.enabled = berp
        return s

    def test_all_disabled_returns_four_nones(self):
        result = _build_simple_graph_caches(self._settings(), [], set())
        self.assertEqual(result, (None, None, None, None))

    def test_kmig_enabled_calls_katz_builder(self):
        fake_cache = object()
        with patch(
            "apps.pipeline.services.pipeline_data.build_katz_cache",
            return_value=fake_cache,
        ):
            katz, apoint, kcore, bridge = _build_simple_graph_caches(
                self._settings(kmig=True), [(1, "post")], set()
            )
        self.assertIs(katz, fake_cache)
        self.assertIsNone(apoint)
        self.assertIsNone(kcore)
        self.assertIsNone(bridge)


# ---------------------------------------------------------------------------
# _build_silo_cache_if_enabled
# ---------------------------------------------------------------------------


class BuildSiloCacheIfEnabledTests(SimpleTestCase):
    """Returns None immediately when HGTE signal is disabled."""

    def test_disabled_returns_none(self):
        settings = MagicMock()
        settings.hgte.enabled = False
        result = _build_silo_cache_if_enabled(settings, {}, set())
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _build_query_cache_if_enabled
# ---------------------------------------------------------------------------


class BuildQueryCacheIfEnabledTests(SimpleTestCase):
    """Returns None immediately when RSQVA signal is disabled."""

    def test_disabled_returns_none(self):
        settings = MagicMock()
        settings.rsqva.enabled = False
        result = _build_query_cache_if_enabled(settings, {})
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _score_keyword_stuffing_if_enabled
# ---------------------------------------------------------------------------


class ScoreKeywordStuffingIfEnabledTests(SimpleTestCase):
    """Mutating helper is a no-op when keyword_baseline is absent."""

    def test_no_baseline_does_not_mutate(self):
        content_data = {"keyword_baseline": None, "keyword_stuffing_by_destination": {}}
        _score_keyword_stuffing_if_enabled(content_data, MagicMock(), lambda *a: None)
        self.assertEqual(content_data["keyword_stuffing_by_destination"], {})

    def test_with_baseline_populates_scores(self):
        record = MagicMock()
        content_data = {
            "keyword_baseline": MagicMock(),
            "keyword_stuffing_by_destination": {},
            "content_records": {(1, "post"): record},
        }
        fake_score = {"score": 0.3}
        with patch(
            "apps.pipeline.services.pipeline_data.evaluate_keyword_stuffing",
            return_value=fake_score,
        ):
            _score_keyword_stuffing_if_enabled(
                content_data, MagicMock(), lambda *a: None
            )
        self.assertIn((1, "post"), content_data["keyword_stuffing_by_destination"])


# ---------------------------------------------------------------------------
# _detect_link_farm_if_enabled
# ---------------------------------------------------------------------------


class DetectLinkFarmIfEnabledTests(SimpleTestCase):
    """Mutating helper is a no-op when link_farm is disabled."""

    def test_disabled_does_not_mutate(self):
        content_data = {"link_farm_by_destination": {}, "existing_links": set()}
        settings = MagicMock()
        settings.enabled = False
        _detect_link_farm_if_enabled(content_data, settings, lambda *a: None)
        self.assertEqual(content_data["link_farm_by_destination"], {})

    def test_enabled_calls_detector(self):
        content_data = {"link_farm_by_destination": {}, "existing_links": {("a", "b")}}
        settings = MagicMock()
        settings.enabled = True
        fake_rings = {(1, "post"): ["ring1"]}
        with patch(
            "apps.pipeline.services.pipeline_data.detect_link_farm_rings",
            return_value=fake_rings,
        ):
            _detect_link_farm_if_enabled(content_data, settings, lambda *a: None)
        self.assertIs(content_data["link_farm_by_destination"], fake_rings)


# ---------------------------------------------------------------------------
# _load_rare_term_profiles
# ---------------------------------------------------------------------------


class LoadRareTermProfilesTests(SimpleTestCase):
    """Returns empty dict immediately when rare_term is disabled."""

    def test_disabled_returns_empty_dict(self):
        settings = MagicMock()
        settings.enabled = False
        result = _load_rare_term_profiles(settings, {}, None, None, None, lambda *a: None)
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# _load_keyword_baseline_if_enabled
# ---------------------------------------------------------------------------


class LoadKeywordBaselineIfEnabledTests(SimpleTestCase):
    """Returns None immediately when keyword_stuffing is disabled."""

    def test_disabled_returns_none(self):
        settings = MagicMock()
        settings.enabled = False
        result = _load_keyword_baseline_if_enabled(settings, {}, None, None, None)
        self.assertIsNone(result)
