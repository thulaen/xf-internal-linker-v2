import ctypes
import json
import math
import os
from collections import Counter
from contextlib import ExitStack
from dataclasses import replace
from datetime import timedelta
from time import perf_counter
from unittest.mock import ANY, MagicMock, patch

import numpy as np
from scipy.sparse import csr_matrix
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.content.models import ContentItem, Post, ScopeItem, Sentence, SiloGroup
from apps.pipeline.services.click_distance import (
    ClickDistanceService,
    ClickDistanceSettings,
)
from apps.pipeline import tasks as pipeline_tasks
from apps.pipeline.services import pipeline as pipeline_service
from apps.pipeline.services import ranker as ranker_service
from apps.pipeline.services import text_tokens as text_tokens_service
from apps.pipeline.services import field_aware_relevance as field_aware_service
from apps.pipeline.services import link_parser as link_parser_service
from apps.pipeline.services import rare_term_propagation as rare_term_service
from apps.pipeline.services import weighted_pagerank as weighted_pagerank_service
from apps.pipeline.services.feedback_rerank import (
    FeedbackRerankService,
    FeedbackRerankSettings,
)
from apps.core.models import AppSetting
from apps.graph.models import BrokenLink, ExistingLink
from apps.pipeline.services.field_aware_relevance import (
    FieldAwareRelevanceSettings,
    evaluate_field_aware_relevance,
)
from apps.pipeline.services.learned_anchor import (
    LearnedAnchorInputRow,
    LearnedAnchorSettings,
    evaluate_learned_anchor_corroboration,
)
from apps.pipeline.services.link_freshness import (
    LinkFreshnessPeerRow,
    LinkFreshnessSettings,
    calculate_link_freshness,
    run_link_freshness,
)
from apps.pipeline.services.phrase_matching import (
    PhraseMatchingSettings,
    _build_destination_phrase_inventory,
    evaluate_phrase_match,
)
from apps.pipeline.services.rare_term_propagation import (
    RareTermPropagationSettings,
    build_rare_term_profiles,
    evaluate_rare_term_propagation,
)
from apps.pipeline.services.pipeline import (
    DEFAULT_WEIGHTS,
    PipelineResult,
    _load_sentence_embeddings,
    _load_sentence_records,
    _load_weights,
    _persist_diagnostics,
    _persist_suggestions,
    _score_sentences_stage2,
)
from apps.pipeline.services.ranker import (
    ClusteringSettings,
    ContentRecord,
    ScoredCandidate,
    SentenceRecord,
    SentenceSemanticMatch,
    SiloSettings,
    score_destination_matches,
)
from apps.pipeline.services.slate_diversity import SlateDiversitySettings
from apps.pipeline.services.slate_diversity import apply_slate_diversity, get_slate_diversity_runtime_status
from apps.pipeline.services.weighted_pagerank import (
    _WeightedEdge,
    _normalize_source_edges,
    run_weighted_pagerank,
)
from apps.suggestions.models import PipelineDiagnostic, PipelineRun, Suggestion

try:
    from extensions import scoring as scoring_ext
except ImportError:
    scoring_ext = None

try:
    from extensions import texttok as texttok_ext
except ImportError:
    texttok_ext = None

try:
    from extensions import simsearch as simsearch_ext
except ImportError:
    simsearch_ext = None

try:
    from extensions import pagerank as pagerank_ext
except ImportError:
    pagerank_ext = None

try:
    from extensions import phrasematch as phrasematch_ext
except ImportError:
    phrasematch_ext = None

try:
    from extensions import fieldrel as fieldrel_ext
except ImportError:
    fieldrel_ext = None

try:
    from extensions import rareterm as rareterm_ext
except ImportError:
    rareterm_ext = None

try:
    from extensions import linkparse as linkparse_ext
except ImportError:
    linkparse_ext = None

try:
    from extensions import feedrerank as feedrerank_ext
except ImportError:
    feedrerank_ext = None


def _peak_working_set_bytes() -> int:
    if os.name == "nt":
        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_uint32),
                ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.WinDLL("psapi")
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        ok = psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        if ok:
            return max(int(counters.PeakWorkingSetSize), int(counters.WorkingSetSize))
        return 0

    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        peak = int(usage.ru_maxrss)
        return peak if peak > 10_000_000 else peak * 1024
    except Exception:
        return 0


def _content_record(
    *,
    content_id: int,
    silo_group_id: int | None,
    march_2026_pagerank_score: float = 0.0,
    link_freshness_score: float = 0.5,
    content_value_score: float = 0.0,
) -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        content_type="thread",
        title=f"Item {content_id}",
        distilled_text="Topic body",
        scope_id=content_id,
        scope_type="node",
        parent_id=None,
        parent_type="",
        grandparent_id=None,
        grandparent_type="",
        silo_group_id=silo_group_id,
        silo_group_name=f"Silo {silo_group_id}" if silo_group_id else "",
        reply_count=5,
        march_2026_pagerank_score=march_2026_pagerank_score,
        link_freshness_score=link_freshness_score,
        content_value_score=content_value_score,
        primary_post_char_count=500,
        tokens=frozenset({"topic", str(content_id)}),
    )


def _scored_candidate(
    *,
    destination_content_id: int,
    host_content_id: int,
    host_sentence_id: int,
    score_final: float = 1.0,
    score_click_distance: float = 0.5,
    score_explore_exploit: float = 0.5,
    click_distance_diagnostics: dict[str, object] | None = None,
    explore_exploit_diagnostics: dict[str, object] | None = None,
    phrase_match_diagnostics: dict[str, object] | None = None,
    learned_anchor_diagnostics: dict[str, object] | None = None,
    rare_term_diagnostics: dict[str, object] | None = None,
    field_aware_diagnostics: dict[str, object] | None = None,
    cluster_diagnostics: dict[str, object] | None = None,
) -> ScoredCandidate:
    return ScoredCandidate(
        destination_content_id=destination_content_id,
        destination_content_type="thread",
        host_content_id=host_content_id,
        host_content_type="thread",
        host_sentence_id=host_sentence_id,
        score_semantic=0.81,
        score_keyword=0.31,
        score_node_affinity=0.21,
        score_quality=0.41,
        score_silo_affinity=0.0,
        score_phrase_relevance=0.77,
        score_learned_anchor_corroboration=0.73,
        score_rare_term_propagation=0.69,
        score_field_aware_relevance=0.66,
        score_ga4_gsc=0.62,
        score_click_distance=score_click_distance,
        score_explore_exploit=score_explore_exploit,
        score_cluster_suppression=0.0,
        score_final=score_final,
        anchor_phrase="internal link",
        anchor_start=3,
        anchor_end=16,
        anchor_confidence="strong",
        phrase_match_diagnostics=phrase_match_diagnostics or {"phrase_match_state": "computed_exact_title"},
        learned_anchor_diagnostics=learned_anchor_diagnostics or {"learned_anchor_state": "exact_variant_match"},
        rare_term_diagnostics=rare_term_diagnostics or {"rare_term_state": "computed_match"},
        field_aware_diagnostics=field_aware_diagnostics or {"field_aware_state": "computed_match"},
        cluster_diagnostics=cluster_diagnostics or {},
        explore_exploit_diagnostics=explore_exploit_diagnostics or {"final_factor": 1.25},
        click_distance_diagnostics=click_distance_diagnostics or {"score_component": 0.4},
    )


class ScoringExtensionTests(TestCase):
    def _assert_full_batch_matches_reference(self, component_count: int) -> None:
        if scoring_ext is None or not hasattr(scoring_ext, "calculate_composite_scores_full_batch"):
            self.skipTest("C++ extension not compiled")

        np.random.seed(42)
        component_scores = np.random.uniform(-1.0, 1.0, size=(50, component_count)).astype(np.float32)
        weights = np.random.uniform(-0.75, 0.75, size=(component_count,)).astype(np.float32)
        silo = np.random.uniform(-0.5, 0.5, size=(50,)).astype(np.float32)

        py_result = ranker_service._calculate_composite_scores_full_batch_py(
            component_scores,
            weights,
            silo,
        )
        cpp_result = scoring_ext.calculate_composite_scores_full_batch(
            component_scores,
            weights,
            silo,
        )

        np.testing.assert_allclose(cpp_result, py_result, atol=1e-6, rtol=0.0)

    def test_full_batch_scoring_matches_python_reference_with_12_columns(self):
        self._assert_full_batch_matches_reference(component_count=12)

    def test_full_batch_scoring_matches_python_reference_with_5_columns(self):
        self._assert_full_batch_matches_reference(component_count=5)

    def test_feedrerank_mmr_batch_matches_python_reference(self):
        if feedrerank_ext is None or not hasattr(feedrerank_ext, "calculate_mmr_scores_batch"):
            self.skipTest("C++ feed rerank extension not compiled")

        relevance = np.array([0.95, 0.8, 0.6], dtype=np.float64)
        candidate_embeddings = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float64,
        )
        selected_embeddings = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        diversity_lambda = 0.65

        cpp_scores, cpp_max_sims = feedrerank_ext.calculate_mmr_scores_batch(
            relevance,
            candidate_embeddings,
            selected_embeddings,
            diversity_lambda,
        )

        py_max_sims = np.array(
            [
                max(float(np.dot(candidate, selected)) for selected in selected_embeddings)
                for candidate in candidate_embeddings
            ],
            dtype=np.float64,
        )
        py_scores = (diversity_lambda * relevance) - ((1.0 - diversity_lambda) * py_max_sims)

        np.testing.assert_allclose(cpp_max_sims, py_max_sims, atol=1e-9, rtol=0.0)
        np.testing.assert_allclose(cpp_scores, py_scores, atol=1e-9, rtol=0.0)


class TextTokenizerExtensionTests(TestCase):
    def test_batch_tokenizer_matches_python_reference(self):
        if texttok_ext is None or not hasattr(texttok_ext, "tokenize_text_batch"):
            self.skipTest("C++ extension not compiled")

        texts = [
            "",
            "the and or but",
            "don't stop believing",
            "can't stop won't stop",
            "it's a test",
            "Hello WORLD",
            "abc123 xyz789",
            "cafe",
            "café",
            "café and tea",
            "A typical sentence for token testing.",
            "Numbers 123 456 and words",
            "Mixed CASE and Don't Repeat don't repeat",
            "one,two;three",
            "rock'n'roll",
            "URL http://example.com/path",
            "Email me@example.com now",
            "Quote 'single' and apostrophe don't",
            "Tabs\tand\nnewlines",
            "Repeat repeat REPEAT unique",
        ]

        py_result = text_tokens_service.tokenize_text_batch(
            texts,
            text_tokens_service.STANDARD_ENGLISH_STOPWORDS,
        )
        cpp_result = texttok_ext.tokenize_text_batch(
            texts,
            text_tokens_service.STANDARD_ENGLISH_STOPWORDS,
        )

        self.assertEqual(len(cpp_result), len(py_result))
        for cpp_tokens, py_tokens in zip(cpp_result, py_result, strict=True):
            self.assertEqual(cpp_tokens, py_tokens)


class TextTokenizerServiceTests(TestCase):
    def test_tokenize_text_filters_stopwords_and_keeps_ascii_apostrophe_tokens(self):
        result = text_tokens_service.tokenize_text("Don't stop the internal linking guide")
        self.assertEqual(
            result,
            frozenset({"stop", "internal", "linking", "guide"}),
        )


class PipelineLoaderTests(TestCase):
    @override_settings(HOST_SCAN_WORD_LIMIT=20)
    def test_sentence_loaders_honor_word_limit_without_loading_extra_rows(self):
        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Scope")
        content = ContentItem.objects.create(
            content_id=101,
            content_type="thread",
            title="Thread",
            scope=scope,
            distilled_text="Body",
        )
        post = Post.objects.create(
            content_item=content,
            raw_bbcode="[b]Body[/b]",
            clean_text="Short sentence. This one is out of range.",
            char_count=39,
        )
        first_sentence = Sentence.objects.create(
            content_item=content,
            post=post,
            text="Short sentence.",
            position=0,
            char_count=15,
            start_char=0,
            end_char=15,
            word_position=5,
            embedding=[0.25] * 1024,
        )
        Sentence.objects.create(
            content_item=content,
            post=post,
            text="This one is out of range.",
            position=1,
            char_count=25,
            start_char=16,
            end_char=41,
            word_position=50,
            embedding=[0.75] * 1024,
        )

        content_keys = {(content.pk, content.content_type)}

        sentence_records, content_to_sentence_ids = _load_sentence_records(content_keys)
        sentence_ids, sentence_embeddings = _load_sentence_embeddings(content_keys)

        self.assertEqual(list(sentence_records.keys()), [first_sentence.pk])
        self.assertEqual(
            list(content_to_sentence_ids[(content.pk, content.content_type)]),
            [first_sentence.pk],
        )
        self.assertEqual(sentence_ids, [first_sentence.pk])
        self.assertEqual(sentence_embeddings.shape, (1, 1024))


class SimsearchExtensionTests(TestCase):
    def test_score_and_topk_matches_numpy_reference(self):
        if simsearch_ext is None or not hasattr(simsearch_ext, "score_and_topk"):
            self.skipTest("C++ extension not compiled")

        np.random.seed(42)
        sentence_embeddings = np.random.uniform(-1.0, 1.0, size=(200, 64)).astype(np.float32)
        destination_embedding = np.random.uniform(-1.0, 1.0, size=(64,)).astype(np.float32)
        candidate_rows = [
            3, 7, 11, 19, 24, 28, 33, 41, 47, 52,
            58, 63, 71, 76, 84, 89, 97, 103, 111, 118,
            126, 133, 141, 148, 152, 167, 173, 181, 188, 196,
        ]

        candidate_matrix = sentence_embeddings[candidate_rows]
        scores = candidate_matrix @ destination_embedding
        top_idx = np.argpartition(scores, -5)[-5:]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        expected_scores = scores[top_idx]

        cpp_idx, cpp_scores = simsearch_ext.score_and_topk(
            destination_embedding,
            sentence_embeddings,
            candidate_rows,
            5,
        )

        np.testing.assert_array_equal(cpp_idx, top_idx)
        np.testing.assert_allclose(cpp_scores, expected_scores, atol=1e-6, rtol=0.0)


class PagerankExtensionTests(TestCase):
    def test_pagerank_step_matches_python_reference_after_20_iterations(self):
        if pagerank_ext is None or not hasattr(pagerank_ext, "pagerank_step"):
            self.skipTest("C++ extension not compiled")

        rows = np.array([1, 2, 2, 3, 4, 5, 5, 6, 7, 8, 9, 0, 9, 4], dtype=np.int32)
        cols = np.array([0, 0, 1, 2, 2, 3, 4, 5, 5, 6, 7, 8, 8, 9], dtype=np.int32)
        data = np.array([1.0, 0.4, 0.6, 1.0, 1.0, 0.7, 0.3, 1.0, 1.0, 1.0, 1.0, 0.5, 0.5, 1.0], dtype=np.float64)
        adjacency = csr_matrix((data, (rows, cols)), shape=(10, 10), dtype=np.float64)
        dangling_mask = np.array([False, False, False, False, False, False, False, False, False, False], dtype=bool)
        damping = 0.15

        py_ranks = np.full(10, 0.1, dtype=np.float64)
        cpp_ranks = np.full(10, 0.1, dtype=np.float64)

        for _ in range(20):
            py_ranks, _ = weighted_pagerank_service._pagerank_step_py(
                indptr=adjacency.indptr.astype(np.int32),
                indices=adjacency.indices.astype(np.int32),
                data=adjacency.data.astype(np.float64),
                ranks=py_ranks,
                dangling_mask=dangling_mask,
                damping=damping,
                node_count=10,
            )
            cpp_ranks, _ = pagerank_ext.pagerank_step(
                adjacency.indptr.astype(np.int32),
                adjacency.indices.astype(np.int32),
                adjacency.data.astype(np.float64),
                cpp_ranks,
                dangling_mask,
                damping,
                10,
            )

        np.testing.assert_allclose(cpp_ranks, py_ranks, atol=1e-6, rtol=0.0)


class PhraseMatchExtensionTests(TestCase):
    def test_longest_contiguous_overlap_matches_python_reference(self):
        if phrasematch_ext is None or not hasattr(phrasematch_ext, "longest_contiguous_overlap"):
            self.skipTest("C++ extension not compiled")

        cases = [
            ([], [], 0),
            ([], ["a"], 0),
            (["a"], [], 0),
            (["a", "b", "c"], ["a", "b", "c"], 3),
            (["a", "b"], ["x", "y"], 0),
            (["a", "b", "c"], ["a", "b", "x"], 2),
            (["x", "a", "b", "c", "y"], ["q", "a", "b", "c", "r"], 3),
            (["x", "y", "a", "b"], ["q", "a", "b"], 2),
            (["solo"], ["solo", "pair"], 1),
            (["guide", "internal", "links"], ["internal", "links", "guide"], 2),
        ]

        for left, right, expected in cases:
            best = 0
            for left_start in range(len(left)):
                for right_start in range(len(right)):
                    match_len = 0
                    while (
                        left_start + match_len < len(left)
                        and right_start + match_len < len(right)
                        and left[left_start + match_len] == right[right_start + match_len]
                    ):
                        match_len += 1
                    if match_len > best:
                        best = match_len
            py_result = best
            cpp_result = phrasematch_ext.longest_contiguous_overlap(left, right)
            self.assertEqual(py_result, expected)
            self.assertEqual(cpp_result, py_result)


class FieldRelExtensionTests(TestCase):
    def test_score_field_tokens_matches_python_reference_profiles(self):
        if fieldrel_ext is None or not hasattr(fieldrel_ext, "score_field_tokens"):
            self.skipTest("C++ extension not compiled")

        profiles = [
            {
                "profile": field_aware_service._FieldProfile(
                    name="title",
                    token_counts=Counter({"alpha": 2, "beta": 1}),
                    field_length=3,
                    field_weight=0.4,
                    b_value=field_aware_service.TITLE_B,
                ),
                "host_token_counts": Counter({"alpha": 10, "beta": 1}),
                "field_presence_count": Counter({"alpha": 1, "beta": 2}),
            },
            {
                "profile": field_aware_service._FieldProfile(
                    name="body",
                    token_counts=Counter({"longform": 6, "guide": 2, "editor": 1}),
                    field_length=90,
                    field_weight=0.3,
                    b_value=field_aware_service.BODY_B,
                ),
                "host_token_counts": Counter({"longform": 2, "guide": 1, "editor": 1}),
                "field_presence_count": Counter({"longform": 1, "guide": 2, "editor": 4}),
            },
            {
                "profile": field_aware_service._FieldProfile(
                    name="scope",
                    token_counts=Counter({"alpha": 2, "alpine": 2, "atom": 1}),
                    field_length=5,
                    field_weight=0.15,
                    b_value=field_aware_service.SCOPE_B,
                ),
                "host_token_counts": Counter({"alpha": 1, "alpine": 1, "atom": 1}),
                "field_presence_count": Counter({"alpha": 2, "alpine": 2, "atom": 2}),
            },
        ]

        for case in profiles:
            profile = case["profile"]
            host_token_counts = case["host_token_counts"]
            field_presence_count = case["field_presence_count"]
            matched_tokens = []
            host_tfs = []
            field_tfs = []
            field_presence_counts = []
            for token, host_tf in host_token_counts.items():
                field_tf = profile.token_counts.get(token, 0)
                if field_tf <= 0:
                    continue
                matched_tokens.append(token)
                host_tfs.append(int(host_tf))
                field_tfs.append(int(field_tf))
                field_presence_counts.append(int(field_presence_count.get(token, 0)))

            cpp_score = fieldrel_ext.score_field_tokens(
                matched_tokens,
                host_tfs,
                field_tfs,
                field_presence_counts,
                profile.field_length,
                field_aware_service.REFERENCE_FIELD_LENGTHS[profile.name],
                profile.b_value,
                field_aware_service.FIELD_COUNT,
                field_aware_service.BM25_K1,
                field_aware_service.MAX_MATCHED_TOKENS_PER_FIELD,
            )

            with patch.object(field_aware_service, "HAS_CPP_EXT", False):
                py_score, _ = field_aware_service._score_field(
                    profile=profile,
                    host_token_counts=host_token_counts,
                    field_presence_count=field_presence_count,
                )

            self.assertAlmostEqual(cpp_score, py_score, places=6)


class RareTermExtensionTests(TestCase):
    def test_evaluate_rare_terms_matches_python_reference_profiles(self):
        if rareterm_ext is None or not hasattr(rareterm_ext, "evaluate_rare_terms"):
            self.skipTest("C++ extension not compiled")

        cases = [
            (
                ["xenforo", "plugin"],
                [0.8, 0.6],
                [3, 2],
                frozenset({"xenforo"}),
            ),
            (
                ["anchor", "signal"],
                [0.7, 0.4],
                [2, 2],
                frozenset({"anchor", "signal"}),
            ),
            (
                ["alpine", "alpha", "atom"],
                [0.9, 0.9, 0.9],
                [2, 2, 2],
                frozenset({"alpha", "alpine", "atom"}),
            ),
            (
                ["guide", "workflow"],
                [0.3, 0.2],
                [1, 1],
                frozenset({"missing"}),
            ),
            (
                ["scope", "cluster", "rank"],
                [0.55, 0.75, 0.65],
                [1, 4, 2],
                frozenset({"scope", "rank"}),
            ),
            (
                ["freshness"],
                [0.51],
                [2],
                frozenset({"freshness"}),
            ),
            (
                ["learned", "anchor", "rare"],
                [0.61, 0.62, 0.63],
                [2, 3, 4],
                frozenset({"learned", "anchor"}),
            ),
            (
                ["query", "click", "distance"],
                [0.42, 0.52, 0.62],
                [1, 2, 3],
                frozenset({"distance"}),
            ),
            (
                ["family", "support"],
                [0.88, 0.88],
                [4, 3],
                frozenset({"family", "support"}),
            ),
            (
                ["alpha", "beta", "gamma"],
                [0.5, 0.5, 0.5],
                [2, 2, 2],
                frozenset({"beta", "gamma"}),
            ),
        ]

        for index, (terms, evidences, supporting_pages, host_tokens) in enumerate(cases, start=1):
            destination = _content_record(content_id=900 + index, silo_group_id=None)
            profile = rare_term_service.RareTermProfile(
                destination_key=destination.key,
                profile_state="profile_ready",
                original_destination_terms=(),
                eligible_related_page_count=3,
                related_page_summary=(),
                propagated_terms=tuple(
                    rare_term_service.PropagatedRareTerm(
                        term=term,
                        document_frequency=1,
                        supporting_related_pages=pages,
                        supporting_relationship_weights=(1.0,),
                        average_relationship_weight=1.0,
                        term_evidence=evidence,
                    )
                    for term, evidence, pages in zip(terms, evidences, supporting_pages, strict=True)
                ),
            )

            cpp_matched, cpp_score = rareterm_ext.evaluate_rare_terms(
                terms,
                evidences,
                supporting_pages,
                host_tokens,
                rare_term_service.MAX_TERMS_PER_SUGGESTION,
            )

            with patch.object(rare_term_service, "HAS_CPP_EXT", False):
                py_result = rare_term_service._evaluate_rare_term_propagation(
                    destination=destination,
                    host_sentence_tokens=host_tokens,
                    profiles={destination.key: profile},
                    settings=rare_term_service.RareTermPropagationSettings(enabled=True),
                )

            self.assertEqual(cpp_matched, py_result.rare_term_state == "computed_match")
            if cpp_matched:
                self.assertAlmostEqual(cpp_score, py_result.score_rare_term_propagation, places=6)
            else:
                self.assertAlmostEqual(cpp_score, 0.0, places=6)


class LinkParseExtensionTests(TestCase):
    def test_find_urls_matches_python_reference_cases(self):
        if linkparse_ext is None or not hasattr(linkparse_ext, "find_urls"):
            self.skipTest("C++ extension not compiled")

        cases = [
            "",
            "[URL=https://example.com/threads/topic.1]Anchor[/URL]",
            "[url=https://example.com/threads/topic.2]Lower[/url]",
            "<a href=\"https://example.com/resources/tool.3\">Tool</a>",
            "Visit https://example.com/threads/topic.4 now",
            "[URL=https://example.com/threads/topic.5]<b>Bold</b> anchor[/URL]",
            "<a class=\"x\" href='https://example.com/resources/tool.6'>Inner <b>tag</b></a>",
            "[URL=https://example.com/threads/topic.7]<a href=\"https://bad\">Nested</a>[/URL>",
            "[URL=https://example.com/threads/topic.8][/URL]",
            "Before <a href=\"https://example.com/threads/topic.9?x=1#frag\">Query</a> after",
            "Mix [url=https://example.com/threads/topic.10]One[/url] and https://example.com/resources/tool.10",
            "No urls here at all",
            "Overlap <a href=\"https://example.com/threads/topic.11\">https://example.com/resources/tool.11</a>",
            "[URL=https://example.com/threads/topic.12]Upper[/URL] <A HREF=\"https://example.com/resources/tool.12\">Html</A>",
            "Two bare URLs https://example.com/threads/topic.13 and https://example.com/resources/tool.13",
        ]

        for text in cases:
            py_result = [
                (link.url, link.anchor_text, link.extraction_method, link.start, link.end)
                for link in link_parser_service._find_urls_py(text)
            ]
            cpp_result = linkparse_ext.find_urls(text)
            self.assertEqual(cpp_result, py_result)


class FeedRerankExtensionTests(TestCase):
    def test_calculate_rerank_factors_batch_matches_python_reference(self):
        if feedrerank_ext is None or not hasattr(feedrerank_ext, "calculate_rerank_factors_batch"):
            self.skipTest("C++ extension not compiled")

        np.random.seed(42)
        n_totals = np.random.randint(0, 50, size=100, dtype=np.int32)
        n_successes = np.array(
            [np.random.randint(0, int(total) + 1) for total in n_totals],
            dtype=np.int32,
        )
        n_global = 250
        alpha = 1.0
        beta = 1.0
        weight = 0.2
        exploration_rate = 1.0

        service = FeedbackRerankService(
            FeedbackRerankSettings(
                enabled=True,
                ranking_weight=weight,
                exploration_rate=exploration_rate,
                alpha_prior=alpha,
                beta_prior=beta,
            )
        )
        expected = []
        for successes, total in zip(n_successes.tolist(), n_totals.tolist(), strict=True):
            service._pair_stats[(1, 1)] = {"total": total, "successes": successes}
            service._global_total_samples = n_global
            factor, _ = service.calculate_rerank_factor(1, 1)
            expected.append(factor)

        cpp_result = feedrerank_ext.calculate_rerank_factors_batch(
            n_successes,
            n_totals,
            n_global,
            alpha,
            beta,
            weight,
            exploration_rate,
        )

        np.testing.assert_allclose(cpp_result, np.asarray(expected, dtype=np.float64), atol=1e-6, rtol=0.0)


class SiloRankerTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=1, silo_group_id=10)
        self.same_host = _content_record(content_id=2, silo_group_id=10)
        self.cross_host = _content_record(content_id=3, silo_group_id=99)
        self.unassigned_host = _content_record(content_id=4, silo_group_id=None)
        self.sentence_records = {
            20: SentenceRecord(20, 2, "thread", "Useful same silo sentence", 80, frozenset({"topic"})),
            30: SentenceRecord(30, 3, "thread", "Useful cross silo sentence", 80, frozenset({"topic"})),
            40: SentenceRecord(40, 4, "thread", "Useful unassigned sentence", 80, frozenset({"topic"})),
        }
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.march_2026_pagerank_bounds = (0.1, 2.0)

    def test_prefer_same_silo_adjusts_scores_but_disabled_preserves_baseline(self):
        same_match = [SentenceSemanticMatch(2, "thread", 20, 0.8)]
        cross_match = [SentenceSemanticMatch(3, "thread", 30, 0.8)]
        records = {
            self.destination.key: self.destination,
            self.same_host.key: self.same_host,
            self.cross_host.key: self.cross_host,
        }

        disabled_same = score_destination_matches(
            self.destination,
            same_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="disabled"),
        )[0]
        disabled_cross = score_destination_matches(
            self.destination,
            cross_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="disabled"),
        )[0]
        preferred_same = score_destination_matches(
            self.destination,
            same_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="prefer_same_silo", same_silo_boost=0.2, cross_silo_penalty=0.1),
        )[0]
        preferred_cross = score_destination_matches(
            self.destination,
            cross_match,
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="prefer_same_silo", same_silo_boost=0.2, cross_silo_penalty=0.1),
        )[0]

        self.assertAlmostEqual(disabled_same.score_silo_affinity, 0.0)
        self.assertAlmostEqual(disabled_cross.score_silo_affinity, 0.0)
        self.assertAlmostEqual(preferred_same.score_silo_affinity, 0.2)
        self.assertAlmostEqual(preferred_cross.score_silo_affinity, -0.1)
        self.assertGreater(preferred_same.score_final, disabled_same.score_final)
        self.assertLess(preferred_cross.score_final, disabled_cross.score_final)

    def test_strict_same_silo_blocks_only_cross_silo_and_emits_reason(self):
        cross_reasons: set[str] = set()
        unassigned_reasons: set[str] = set()
        records = {
            self.destination.key: self.destination,
            self.cross_host.key: self.cross_host,
            self.unassigned_host.key: self.unassigned_host,
        }

        cross_result = score_destination_matches(
            self.destination,
            [SentenceSemanticMatch(3, "thread", 30, 0.8)],
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="strict_same_silo"),
            blocked_reasons=cross_reasons,
        )
        unassigned_result = score_destination_matches(
            self.destination,
            [SentenceSemanticMatch(4, "thread", 40, 0.8)],
            content_records=records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            silo_settings=SiloSettings(mode="strict_same_silo"),
            blocked_reasons=unassigned_reasons,
        )

        self.assertEqual(cross_result, [])
        self.assertIn("cross_silo_blocked", cross_reasons)
        self.assertEqual(len(unassigned_result), 1)
        self.assertEqual(unassigned_reasons, set())

    def test_cross_silo_diagnostic_persists_machine_readable_detail(self):
        run = PipelineRun.objects.create()
        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        destination_silo = SiloGroup.objects.create(name="Guides", slug="guides")
        scope.silo_group = destination_silo
        scope.save(update_fields=["silo_group"])
        destination = ContentItem.objects.create(
            content_id=1,
            content_type="thread",
            title="Guide",
            scope=scope,
        )

        _persist_diagnostics(
            run_id=str(run.run_id),
            diagnostics=[
                (
                    destination.pk,
                    destination.content_type,
                    "cross_silo_blocked",
                    {
                        "mode": "strict_same_silo",
                        "destination_silo_group_id": destination_silo.pk,
                        "destination_silo_group_name": destination_silo.name,
                    },
                )
            ],
        )

        diagnostic = PipelineDiagnostic.objects.get()
        self.assertEqual(diagnostic.skip_reason, "cross_silo_blocked")
        self.assertEqual(diagnostic.detail["mode"], "strict_same_silo")
        self.assertEqual(diagnostic.destination_id, destination.pk)

    def test_weighted_authority_disabled_preserves_existing_ranker_output(self):
        destination = _content_record(content_id=10, silo_group_id=None, march_2026_pagerank_score=2.0)
        host = _content_record(content_id=20, silo_group_id=None)
        records = {
            destination.key: destination,
            host.key: host,
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records=self.sentence_records | {
                20: SentenceRecord(20, 20, "thread", "Useful sentence about topic", 80, frozenset({"topic"}))
            },
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            weighted_authority_ranking_weight=0.0,
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records=self.sentence_records | {
                20: SentenceRecord(20, 20, "thread", "Useful sentence about topic", 80, frozenset({"topic"}))
            },
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            weighted_authority_ranking_weight=0.25,
        )[0]

        self.assertAlmostEqual(baseline.score_final + 0.25, enabled.score_final, places=6)

    def test_weighted_authority_does_not_override_existing_link_block(self):
        destination = _content_record(content_id=10, silo_group_id=None, march_2026_pagerank_score=2.0)
        host = _content_record(content_id=20, silo_group_id=None)
        records = {
            destination.key: destination,
            host.key: host,
        }

        result = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records={
                20: SentenceRecord(20, 20, "thread", "Useful sentence about topic", 80, frozenset({"topic"}))
            },
            existing_links={((20, "thread"), (10, "thread"))},
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            weighted_authority_ranking_weight=0.25,
        )

        self.assertEqual(result, [])

    def test_link_freshness_weight_zero_and_neutral_score_have_no_effect(self):
        destination = _content_record(content_id=10, silo_group_id=None, link_freshness_score=0.5)
        fresh_destination = _content_record(content_id=10, silo_group_id=None, link_freshness_score=0.8)
        host = _content_record(content_id=20, silo_group_id=None)
        records = {
            destination.key: destination,
            host.key: host,
        }
        sentence_records = {
            20: SentenceRecord(20, 20, "thread", "Useful sentence about topic", 80, frozenset({"topic"}))
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            link_freshness_ranking_weight=0.0,
        )[0]
        neutral_enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            link_freshness_ranking_weight=0.15,
        )[0]
        fresh_enabled = score_destination_matches(
            fresh_destination,
            [SentenceSemanticMatch(20, "thread", 20, 0.8)],
            content_records={
                fresh_destination.key: fresh_destination,
                host.key: host,
            },
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            link_freshness_ranking_weight=0.15,
        )[0]

        self.assertAlmostEqual(baseline.score_final, neutral_enabled.score_final, places=6)
        self.assertGreater(fresh_enabled.score_final, baseline.score_final)


class LinkFreshnessServiceTests(TestCase):
    def test_neutral_fallbacks_and_growth_behavior(self):
        now = timezone.now()
        settings = LinkFreshnessSettings()

        missing = calculate_link_freshness([], reference_time=now, settings=settings)
        self.assertEqual(missing.link_freshness_score, 0.5)
        self.assertEqual(missing.freshness_data_state, "neutral_missing_history")

        thin = calculate_link_freshness(
            [
                LinkFreshnessPeerRow(
                    first_seen_at=now - timedelta(days=90),
                    last_seen_at=now - timedelta(days=1),
                    last_disappeared_at=None,
                    is_active=True,
                ),
                LinkFreshnessPeerRow(
                    first_seen_at=now - timedelta(days=60),
                    last_seen_at=now - timedelta(days=1),
                    last_disappeared_at=None,
                    is_active=True,
                ),
            ],
            reference_time=now,
            settings=settings,
        )
        self.assertEqual(thin.link_freshness_score, 0.5)
        self.assertEqual(thin.freshness_data_state, "neutral_thin_history")

        growing = calculate_link_freshness(
            [
                LinkFreshnessPeerRow(now - timedelta(days=75), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=65), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=15), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=10), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=5), now - timedelta(days=1), None, True),
            ],
            reference_time=now,
            settings=settings,
        )
        cooling = calculate_link_freshness(
            [
                LinkFreshnessPeerRow(now - timedelta(days=90), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=55), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=50), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=45), now - timedelta(days=1), None, True),
                LinkFreshnessPeerRow(now - timedelta(days=5), now - timedelta(days=1), None, True),
            ],
            reference_time=now,
            settings=settings,
        )

        self.assertGreater(growing.link_freshness_score, 0.5)
        self.assertLess(cooling.link_freshness_score, 0.5)

    def test_recent_disappearances_reduce_score_and_recalc_does_not_touch_pagerank(self):
        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        destination = ContentItem.objects.create(
            content_id=1,
            content_type="thread",
            title="Destination",
            scope=scope,
            march_2026_pagerank_score=0.77,
        )
        sources = [
            ContentItem.objects.create(content_id=index + 2, content_type="thread", title=f"Source {index}", scope=scope)
            for index in range(4)
        ]
        now = timezone.now()
        from apps.graph.models import LinkFreshnessEdge

        for index, source in enumerate(sources):
            LinkFreshnessEdge.objects.create(
                from_content_item=source,
                to_content_item=destination,
                first_seen_at=now - timedelta(days=70 - (index * 5)),
                last_seen_at=now - timedelta(days=1),
                is_active=True,
            )

        baseline = run_link_freshness(reference_time=now)
        destination.refresh_from_db()
        baseline_score = destination.link_freshness_score

        LinkFreshnessEdge.objects.filter(from_content_item=sources[0]).update(
            is_active=False,
            last_disappeared_at=now - timedelta(days=2),
        )
        LinkFreshnessEdge.objects.filter(from_content_item=sources[1]).update(
            is_active=False,
            last_disappeared_at=now - timedelta(days=3),
        )

        diagnostics = run_link_freshness(reference_time=now)
        destination.refresh_from_db()

        self.assertIn("computed_count", baseline)
        self.assertIn("computed_count", diagnostics)
        self.assertLess(destination.link_freshness_score, baseline_score)
        self.assertAlmostEqual(destination.march_2026_pagerank_score, 0.77, places=6)

    def test_link_freshness_ignores_weighted_authority_and_velocity_settings(self):
        scope = ScopeItem.objects.create(scope_id=9, scope_type="node", title="Forum")
        destination = ContentItem.objects.create(content_id=90, content_type="thread", title="Destination", scope=scope)
        source_a = ContentItem.objects.create(content_id=91, content_type="thread", title="Source A", scope=scope)
        source_b = ContentItem.objects.create(content_id=92, content_type="thread", title="Source B", scope=scope)
        source_c = ContentItem.objects.create(content_id=93, content_type="thread", title="Source C", scope=scope)
        now = timezone.now()
        from apps.graph.models import LinkFreshnessEdge

        LinkFreshnessEdge.objects.bulk_create(
            [
                LinkFreshnessEdge(from_content_item=source_a, to_content_item=destination, first_seen_at=now - timedelta(days=80), last_seen_at=now - timedelta(days=1), is_active=True),
                LinkFreshnessEdge(from_content_item=source_b, to_content_item=destination, first_seen_at=now - timedelta(days=50), last_seen_at=now - timedelta(days=1), is_active=True),
                LinkFreshnessEdge(from_content_item=source_c, to_content_item=destination, first_seen_at=now - timedelta(days=10), last_seen_at=now - timedelta(days=1), is_active=True),
            ]
        )

        run_link_freshness(reference_time=now)
        destination.refresh_from_db()
        baseline = destination.link_freshness_score

        AppSetting.objects.update_or_create(
            key="weighted_authority.position_bias",
            defaults={
                "value": "0.9",
                "value_type": "float",
                "category": "ml",
                "description": "Unrelated weighted authority setting",
            },
        )
        AppSetting.objects.update_or_create(
            key="vel_recency_half_life_days",
            defaults={
                "value": "99",
                "value_type": "float",
                "category": "ml",
                "description": "Unrelated velocity setting",
            },
        )

        run_link_freshness(reference_time=now)
        destination.refresh_from_db()
        self.assertAlmostEqual(destination.link_freshness_score, baseline, places=6)


class PhraseMatchingServiceTests(TestCase):
    def test_destination_phrase_inventory_is_bounded_and_prefers_complete_phrases(self):
        phrases = _build_destination_phrase_inventory(
            destination_title="Internal Linking Guide",
            destination_distilled_text=(
                "Helpful examples for editors. "
                "Phrase block one. Phrase block two. Phrase block three. Phrase block four. "
                "Phrase block five. Phrase block six. Phrase block seven. Phrase block eight. "
                "Phrase block nine. Phrase block ten. Phrase block eleven. Phrase block twelve."
            ),
        )

        token_lists = [phrase.tokens for phrase in phrases]
        self.assertLessEqual(len(phrases), 24)
        self.assertIn(("internal", "linking", "guide"), token_lists)
        self.assertNotIn(("internal", "linking"), token_lists)

    def test_exact_title_and_distilled_phrase_matching(self):
        exact_title = evaluate_phrase_match(
            host_sentence_text="This sentence explains the internal linking guide clearly.",
            destination_title="Internal Linking Guide",
            destination_distilled_text="Helpful overview text.",
            settings=PhraseMatchingSettings(),
        )
        exact_distilled = evaluate_phrase_match(
            host_sentence_text="The article walks through anchor expansion rules step by step.",
            destination_title="Internal Linking",
            destination_distilled_text="Anchor expansion rules for safer internal links.",
            settings=PhraseMatchingSettings(),
        )

        self.assertGreater(exact_title.score_phrase_relevance, 0.5)
        self.assertEqual(exact_title.anchor_confidence, "strong")
        self.assertEqual(
            exact_title.phrase_match_diagnostics["phrase_match_state"],
            "computed_exact_title",
        )
        self.assertGreater(exact_distilled.score_phrase_relevance, 0.5)
        self.assertEqual(exact_distilled.anchor_phrase, "anchor expansion rules")
        self.assertEqual(
            exact_distilled.phrase_match_diagnostics["phrase_match_state"],
            "computed_exact_distilled",
        )

    def test_partial_match_needs_local_corroboration(self):
        accepted = evaluate_phrase_match(
            host_sentence_text="The anchor expansion workflow keeps rules nearby for editors.",
            destination_title="Editorial Linking",
            destination_distilled_text="Anchor expansion rules for editors.",
            settings=PhraseMatchingSettings(),
        )
        neutral = evaluate_phrase_match(
            host_sentence_text="The anchor expansion workflow helps editors every day.",
            destination_title="Editorial Linking",
            destination_distilled_text="Anchor expansion rules for editors.",
            settings=PhraseMatchingSettings(),
        )

        self.assertGreater(accepted.score_phrase_relevance, 0.5)
        self.assertEqual(accepted.anchor_confidence, "weak")
        self.assertEqual(
            accepted.phrase_match_diagnostics["phrase_match_state"],
            "computed_partial_distilled",
        )
        self.assertEqual(neutral.score_phrase_relevance, 0.5)
        self.assertEqual(neutral.anchor_confidence, "none")
        self.assertEqual(
            neutral.phrase_match_diagnostics["phrase_match_state"],
            "neutral_partial_below_threshold",
        )

    def test_neutral_fallback_and_anchor_expansion_rollback(self):
        no_phrases = evaluate_phrase_match(
            host_sentence_text="Tiny words only.",
            destination_title="A An The",
            destination_distilled_text="Of To In",
            settings=PhraseMatchingSettings(),
        )
        fallback = evaluate_phrase_match(
            host_sentence_text="This guide covers synthesizers in detail.",
            destination_title="Synthesizers",
            destination_distilled_text="Extra supporting text.",
            settings=PhraseMatchingSettings(enable_anchor_expansion=False),
        )

        self.assertEqual(no_phrases.score_phrase_relevance, 0.5)
        self.assertEqual(
            no_phrases.phrase_match_diagnostics["phrase_match_state"],
            "neutral_no_destination_phrases",
        )
        self.assertEqual(fallback.anchor_phrase, "synthesizers")
        self.assertEqual(
            fallback.phrase_match_diagnostics["phrase_match_state"],
            "fallback_current_extractor",
        )

    def test_longer_complete_phrase_wins(self):
        result = evaluate_phrase_match(
            host_sentence_text="This internal linking guide explains the full workflow.",
            destination_title="Internal Linking Guide",
            destination_distilled_text="Helpful notes.",
            settings=PhraseMatchingSettings(),
        )

        self.assertEqual(result.anchor_phrase, "internal linking guide")


class LearnedAnchorServiceTests(TestCase):
    def test_exact_family_and_host_canonical_states_are_explainable(self):
        rows = [
            LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
            LearnedAnchorInputRow(source_content_id=2, anchor_text="Internal Linking Guide"),
            LearnedAnchorInputRow(source_content_id=3, anchor_text="Internal Linking Guides"),
            LearnedAnchorInputRow(source_content_id=4, anchor_text="click here"),
        ]

        exact = evaluate_learned_anchor_corroboration(
            candidate_anchor_text="Internal Linking Guide",
            host_sentence_text="This internal linking guide helps editors.",
            inbound_anchor_rows=rows,
            settings=LearnedAnchorSettings(),
        )
        family = evaluate_learned_anchor_corroboration(
            candidate_anchor_text="Internal Linking",
            host_sentence_text="This internal linking helps editors.",
            inbound_anchor_rows=rows,
            settings=LearnedAnchorSettings(),
        )
        host_contains = evaluate_learned_anchor_corroboration(
            candidate_anchor_text="Editor workflow",
            host_sentence_text="This internal linking guide helps editors.",
            inbound_anchor_rows=rows,
            settings=LearnedAnchorSettings(),
        )

        self.assertGreater(exact.score_learned_anchor_corroboration, 0.5)
        self.assertEqual(exact.learned_anchor_diagnostics["learned_anchor_state"], "exact_variant_match")
        self.assertEqual(exact.learned_anchor_diagnostics["usable_inbound_anchor_sources"], 3)
        self.assertGreater(family.score_learned_anchor_corroboration, 0.5)
        self.assertEqual(family.learned_anchor_diagnostics["learned_anchor_state"], "family_match")
        self.assertEqual(host_contains.score_learned_anchor_corroboration, 0.5)
        self.assertEqual(host_contains.learned_anchor_diagnostics["learned_anchor_state"], "host_contains_canonical_variant")
        self.assertEqual(host_contains.learned_anchor_diagnostics["recommended_canonical_anchor"], "Internal Linking Guide")

    def test_thin_history_stays_neutral(self):
        result = evaluate_learned_anchor_corroboration(
            candidate_anchor_text="Internal Linking Guide",
            host_sentence_text="This internal linking guide helps editors.",
            inbound_anchor_rows=[
                LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
            ],
            settings=LearnedAnchorSettings(minimum_anchor_sources=2),
        )

        self.assertEqual(result.score_learned_anchor_corroboration, 0.5)
        self.assertEqual(result.learned_anchor_diagnostics["learned_anchor_state"], "neutral_below_min_sources")


class PhraseRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=101, silo_group_id=None)
        self.host = _content_record(content_id=202, silo_group_id=None)
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)

    def test_phrase_weight_zero_keeps_ranking_unchanged_and_positive_weight_adds_signal(self):
        destination = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Anchor expansion tips for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=self.destination.march_2026_pagerank_score,
            link_freshness_score=self.destination.link_freshness_score,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"internal", "linking", "guide"}),
        )
        host = self.host
        records = {destination.key: destination, host.key: host}
        sentence_records = {
            20: SentenceRecord(
                20,
                host.content_id,
                host.content_type,
                "The internal linking guide gives anchor expansion tips.",
                80,
                frozenset({"internal", "linking", "guide", "anchor", "expansion"}),
            )
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 20, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            phrase_matching_settings=PhraseMatchingSettings(ranking_weight=0.0),
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 20, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            phrase_matching_settings=PhraseMatchingSettings(ranking_weight=0.1),
        )[0]

        self.assertGreater(baseline.score_phrase_relevance, 0.5)
        self.assertAlmostEqual(
            enabled.score_final,
            baseline.score_final + 0.1 * (2 * (baseline.score_phrase_relevance - 0.5)),
            places=6,
        )

    def test_phrase_signal_ignores_weighted_authority_freshness_and_velocity_inputs(self):
        destination_a = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Anchor Expansion Rules",
            distilled_text="Anchor expansion rules for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=0.1,
            link_freshness_score=0.2,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"anchor", "expansion", "rules"}),
        )
        destination_b = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Anchor Expansion Rules",
            distilled_text="Anchor expansion rules for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=2.0,
            link_freshness_score=0.9,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"anchor", "expansion", "rules"}),
        )
        host = ContentRecord(
            content_id=self.host.content_id,
            content_type=self.host.content_type,
            title=self.host.title,
            distilled_text=self.host.distilled_text,
            scope_id=self.host.scope_id,
            scope_type=self.host.scope_type,
            parent_id=self.host.parent_id,
            parent_type=self.host.parent_type,
            grandparent_id=self.host.grandparent_id,
            grandparent_type=self.host.grandparent_type,
            silo_group_id=self.host.silo_group_id,
            silo_group_name=self.host.silo_group_name,
            reply_count=99,
            march_2026_pagerank_score=1.8,
            link_freshness_score=self.host.link_freshness_score,
            primary_post_char_count=900,
            tokens=self.host.tokens,
        )
        sentence_records = {
            30: SentenceRecord(
                30,
                host.content_id,
                host.content_type,
                "The anchor expansion rules help editors write natural links.",
                80,
                frozenset({"anchor", "expansion", "rules", "editors"}),
            )
        }

        result_a = score_destination_matches(
            destination_a,
            [SentenceSemanticMatch(host.content_id, host.content_type, 30, 0.8)],
            content_records={destination_a.key: destination_a, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            weighted_authority_ranking_weight=0.25,
            link_freshness_ranking_weight=0.15,
            phrase_matching_settings=PhraseMatchingSettings(ranking_weight=0.0),
        )[0]
        result_b = score_destination_matches(
            destination_b,
            [SentenceSemanticMatch(host.content_id, host.content_type, 30, 0.8)],
            content_records={destination_b.key: destination_b, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            weighted_authority_ranking_weight=0.25,
            link_freshness_ranking_weight=0.15,
            phrase_matching_settings=PhraseMatchingSettings(ranking_weight=0.0),
        )[0]

        self.assertAlmostEqual(result_a.score_phrase_relevance, result_b.score_phrase_relevance, places=6)
        self.assertEqual(result_a.anchor_phrase, result_b.anchor_phrase)


class LearnedAnchorRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=301, silo_group_id=None)
        self.host = _content_record(content_id=302, silo_group_id=None)
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)
        self.learned_rows = {
            self.destination.key: [
                LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
                LearnedAnchorInputRow(source_content_id=2, anchor_text="Internal Linking Guide"),
                LearnedAnchorInputRow(source_content_id=3, anchor_text="Internal Linking Guides"),
            ]
        }

    def test_learned_anchor_weight_zero_keeps_ranking_unchanged_and_positive_weight_adds_signal(self):
        destination = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Internal linking guide notes for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=self.destination.march_2026_pagerank_score,
            link_freshness_score=self.destination.link_freshness_score,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"internal", "linking", "guide"}),
        )
        records = {destination.key: destination, self.host.key: self.host}
        sentence_records = {
            40: SentenceRecord(
                40,
                self.host.content_id,
                self.host.content_type,
                "The internal linking guide gives editors a safe anchor pattern.",
                80,
                frozenset({"internal", "linking", "guide", "editors", "anchor"}),
            )
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(self.host.content_id, self.host.content_type, 40, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            learned_anchor_settings=LearnedAnchorSettings(ranking_weight=0.0),
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(self.host.content_id, self.host.content_type, 40, 0.8)],
            content_records=records,
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            learned_anchor_settings=LearnedAnchorSettings(ranking_weight=0.1),
        )[0]

        self.assertGreater(baseline.score_learned_anchor_corroboration, 0.5)
        self.assertAlmostEqual(
            enabled.score_final,
            baseline.score_final + 0.1 * (2 * (baseline.score_learned_anchor_corroboration - 0.5)),
            places=6,
        )

    def test_learned_anchor_signal_ignores_authority_freshness_and_velocity_inputs(self):
        destination_a = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Internal linking guide notes for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=0.1,
            link_freshness_score=0.2,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"internal", "linking", "guide"}),
        )
        destination_b = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Internal linking guide notes for editors.",
            scope_id=self.destination.scope_id,
            scope_type=self.destination.scope_type,
            parent_id=self.destination.parent_id,
            parent_type=self.destination.parent_type,
            grandparent_id=self.destination.grandparent_id,
            grandparent_type=self.destination.grandparent_type,
            silo_group_id=self.destination.silo_group_id,
            silo_group_name=self.destination.silo_group_name,
            reply_count=self.destination.reply_count,
            march_2026_pagerank_score=2.0,
            link_freshness_score=0.9,
            primary_post_char_count=self.destination.primary_post_char_count,
            tokens=frozenset({"internal", "linking", "guide"}),
        )
        host = ContentRecord(
            content_id=self.host.content_id,
            content_type=self.host.content_type,
            title=self.host.title,
            distilled_text=self.host.distilled_text,
            scope_id=self.host.scope_id,
            scope_type=self.host.scope_type,
            parent_id=self.host.parent_id,
            parent_type=self.host.parent_type,
            grandparent_id=self.host.grandparent_id,
            grandparent_type=self.host.grandparent_type,
            silo_group_id=self.host.silo_group_id,
            silo_group_name=self.host.silo_group_name,
            reply_count=99,
            march_2026_pagerank_score=1.8,
            link_freshness_score=self.host.link_freshness_score,
            primary_post_char_count=900,
            tokens=self.host.tokens,
        )
        sentence_records = {
            41: SentenceRecord(
                41,
                host.content_id,
                host.content_type,
                "The internal linking guide gives editors a safe anchor pattern.",
                80,
                frozenset({"internal", "linking", "guide", "editors", "anchor"}),
            )
        }

        result_a = score_destination_matches(
            destination_a,
            [SentenceSemanticMatch(host.content_id, host.content_type, 41, 0.8)],
            content_records={destination_a.key: destination_a, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            weighted_authority_ranking_weight=0.25,
            link_freshness_ranking_weight=0.15,
            learned_anchor_settings=LearnedAnchorSettings(ranking_weight=0.0),
        )[0]
        result_b = score_destination_matches(
            destination_b,
            [SentenceSemanticMatch(host.content_id, host.content_type, 41, 0.8)],
            content_records={destination_b.key: destination_b, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            weighted_authority_ranking_weight=0.25,
            link_freshness_ranking_weight=0.15,
            learned_anchor_settings=LearnedAnchorSettings(ranking_weight=0.0),
        )[0]

        self.assertAlmostEqual(
            result_a.score_learned_anchor_corroboration,
            result_b.score_learned_anchor_corroboration,
            places=6,
        )
        self.assertEqual(
            result_a.learned_anchor_diagnostics["matched_family_canonical"],
            result_b.learned_anchor_diagnostics["matched_family_canonical"],
        )


class RareTermPropagationServiceTests(TestCase):
    def _record(
        self,
        *,
        content_id: int,
        scope_id: int,
        parent_id: int | None,
        grandparent_id: int | None,
        silo_group_id: int | None,
        tokens: frozenset[str],
    ) -> ContentRecord:
        return ContentRecord(
            content_id=content_id,
            content_type="thread",
            title=f"Item {content_id}",
            distilled_text="Topic body",
            scope_id=scope_id,
            scope_type="node",
            parent_id=parent_id,
            parent_type="category" if parent_id is not None else "",
            grandparent_id=grandparent_id,
            grandparent_type="category" if grandparent_id is not None else "",
            silo_group_id=silo_group_id,
            silo_group_name=f"Silo {silo_group_id}" if silo_group_id else "",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=tokens,
        )

    def test_related_page_boundaries_and_rare_term_thresholds(self):
        destination = self._record(
            content_id=1,
            scope_id=10,
            parent_id=100,
            grandparent_id=1000,
            silo_group_id=1,
            tokens=frozenset({"guide", "topic"}),
        )
        same_scope = self._record(
            content_id=2,
            scope_id=10,
            parent_id=101,
            grandparent_id=1001,
            silo_group_id=1,
            tokens=frozenset({"guide", "xenforo", "plugin"}),
        )
        same_parent_one_shared = self._record(
            content_id=3,
            scope_id=11,
            parent_id=100,
            grandparent_id=1002,
            silo_group_id=1,
            tokens=frozenset({"guide", "solr"}),
        )
        same_parent_two_shared = self._record(
            content_id=4,
            scope_id=12,
            parent_id=100,
            grandparent_id=1003,
            silo_group_id=1,
            tokens=frozenset({"guide", "topic", "xenforo", "plugin"}),
        )
        same_grandparent_two_shared = self._record(
            content_id=5,
            scope_id=13,
            parent_id=102,
            grandparent_id=1000,
            silo_group_id=1,
            tokens=frozenset({"guide", "topic", "plugin"}),
        )
        cross_silo = self._record(
            content_id=6,
            scope_id=10,
            parent_id=100,
            grandparent_id=1000,
            silo_group_id=9,
            tokens=frozenset({"guide", "topic", "xenforo"}),
        )
        plugin_extra_a = self._record(
            content_id=7,
            scope_id=20,
            parent_id=200,
            grandparent_id=2000,
            silo_group_id=None,
            tokens=frozenset({"plugin", "alpha"}),
        )
        plugin_extra_b = self._record(
            content_id=8,
            scope_id=21,
            parent_id=201,
            grandparent_id=2001,
            silo_group_id=None,
            tokens=frozenset({"plugin", "beta"}),
        )

        profiles = build_rare_term_profiles(
            {
                record.key: record
                for record in [
                    destination,
                    same_scope,
                    same_parent_one_shared,
                    same_parent_two_shared,
                    same_grandparent_two_shared,
                    cross_silo,
                    plugin_extra_a,
                    plugin_extra_b,
                ]
            },
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )

        profile = profiles[destination.key]
        self.assertEqual(profile.eligible_related_page_count, 3)
        self.assertEqual(
            [row.content_id for row in profile.related_page_summary],
            [2, 4, 5],
        )
        self.assertEqual(
            [term.term for term in profile.propagated_terms],
            ["xenforo"],
        )

    def test_duplicate_counting_and_destination_separation_stay_safe(self):
        destination = self._record(
            content_id=20,
            scope_id=30,
            parent_id=300,
            grandparent_id=3000,
            silo_group_id=None,
            tokens=frozenset({"guide", "topic", "xenforo"}),
        )
        donor_a = self._record(
            content_id=21,
            scope_id=30,
            parent_id=301,
            grandparent_id=3001,
            silo_group_id=None,
            tokens=frozenset({"guide", "xenforo", "solr"}),
        )
        donor_b = self._record(
            content_id=22,
            scope_id=30,
            parent_id=302,
            grandparent_id=3002,
            silo_group_id=None,
            tokens=frozenset({"topic", "xenforo", "solr"}),
        )

        profiles = build_rare_term_profiles(
            {record.key: record for record in [destination, donor_a, donor_b]},
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        profile = profiles[destination.key]
        self.assertEqual(profile.profile_state, "neutral_no_rare_terms")
        self.assertEqual(profile.propagated_terms, ())

        thin_destination = self._record(
            content_id=23,
            scope_id=31,
            parent_id=310,
            grandparent_id=3100,
            silo_group_id=None,
            tokens=frozenset({"guide", "topic"}),
        )
        thin_donor = self._record(
            content_id=24,
            scope_id=31,
            parent_id=311,
            grandparent_id=3101,
            silo_group_id=None,
            tokens=frozenset({"guide", "xenforo"}),
        )
        thin_profiles = build_rare_term_profiles(
            {record.key: record for record in [thin_destination, thin_donor]},
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        thin_result = evaluate_rare_term_propagation(
            destination=thin_destination,
            host_sentence_tokens=frozenset({"xenforo"}),
            profiles=thin_profiles,
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        self.assertEqual(thin_result.score_rare_term_propagation, 0.5)
        self.assertEqual(thin_result.rare_term_state, "neutral_below_min_support")

        supported_destination = self._record(
            content_id=25,
            scope_id=32,
            parent_id=320,
            grandparent_id=3200,
            silo_group_id=None,
            tokens=frozenset({"guide", "topic"}),
        )
        supported_donor_a = self._record(
            content_id=26,
            scope_id=32,
            parent_id=321,
            grandparent_id=3201,
            silo_group_id=None,
            tokens=frozenset({"guide", "xenforo"}),
        )
        supported_donor_b = self._record(
            content_id=27,
            scope_id=32,
            parent_id=322,
            grandparent_id=3202,
            silo_group_id=None,
            tokens=frozenset({"topic", "xenforo"}),
        )
        supported_profiles = build_rare_term_profiles(
            {
                record.key: record
                for record in [supported_destination, supported_donor_a, supported_donor_b]
            },
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        supported_result = evaluate_rare_term_propagation(
            destination=supported_destination,
            host_sentence_tokens=frozenset({"xenforo"}),
            profiles=supported_profiles,
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )
        self.assertGreater(supported_result.score_rare_term_propagation, 0.5)
        self.assertEqual(len(supported_result.rare_term_diagnostics["matched_propagated_terms"]), 1)
        self.assertEqual(
            supported_result.rare_term_diagnostics["matched_propagated_terms"][0]["supporting_related_pages"],
            2,
        )

    def test_disabled_feature_stays_neutral(self):
        destination = self._record(
            content_id=40,
            scope_id=40,
            parent_id=400,
            grandparent_id=4000,
            silo_group_id=None,
            tokens=frozenset({"guide", "topic"}),
        )

        result = evaluate_rare_term_propagation(
            destination=destination,
            host_sentence_tokens=frozenset({"xenforo"}),
            profiles={},
            settings=RareTermPropagationSettings(enabled=False),
        )

        self.assertEqual(result.score_rare_term_propagation, 0.5)
        self.assertEqual(result.rare_term_state, "neutral_feature_disabled")
        self.assertEqual(result.rare_term_diagnostics, {})


class RareTermRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=401, silo_group_id=None)
        self.host = _content_record(content_id=402, silo_group_id=None)
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)

    def test_rare_term_weight_zero_is_a_ranking_no_op(self):
        destination = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Link Guide",
            distilled_text="Internal link guide for editors.",
            scope_id=500,
            scope_type="node",
            parent_id=900,
            parent_type="category",
            grandparent_id=1200,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"guide", "internal", "link"}),
        )
        donor_a = ContentRecord(
            content_id=403,
            content_type="thread",
            title="XenForo linking notes",
            distilled_text="Guide xenforo notes.",
            scope_id=500,
            scope_type="node",
            parent_id=901,
            parent_type="category",
            grandparent_id=1201,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"guide", "xenforo"}),
        )
        donor_b = ContentRecord(
            content_id=404,
            content_type="thread",
            title="Topic xenforo setup",
            distilled_text="Link xenforo setup.",
            scope_id=500,
            scope_type="node",
            parent_id=902,
            parent_type="category",
            grandparent_id=1202,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"link", "xenforo"}),
        )
        host = ContentRecord(
            content_id=self.host.content_id,
            content_type=self.host.content_type,
            title=self.host.title,
            distilled_text=self.host.distilled_text,
            scope_id=self.host.scope_id,
            scope_type=self.host.scope_type,
            parent_id=self.host.parent_id,
            parent_type=self.host.parent_type,
            grandparent_id=self.host.grandparent_id,
            grandparent_type=self.host.grandparent_type,
            silo_group_id=self.host.silo_group_id,
            silo_group_name=self.host.silo_group_name,
            reply_count=99,
            march_2026_pagerank_score=1.8,
            link_freshness_score=self.host.link_freshness_score,
            primary_post_char_count=900,
            tokens=frozenset({"guide", "link", "xenforo"}),
        )
        sentence_records = {
            50: SentenceRecord(
                50,
                host.content_id,
                host.content_type,
                "This xenforo xenforo guide helps editors manage internal links.",
                80,
                frozenset({"guide", "link", "xenforo", "editors", "internal"}),
            )
        }
        rare_term_profiles = build_rare_term_profiles(
            {
                record.key: record
                for record in [destination, donor_a, donor_b]
            },
            settings=RareTermPropagationSettings(
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 50, 0.8)],
            content_records={destination.key: destination, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            rare_term_profiles=rare_term_profiles,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            rare_term_settings=RareTermPropagationSettings(
                ranking_weight=0.0,
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 50, 0.8)],
            content_records={destination.key: destination, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            rare_term_profiles=rare_term_profiles,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            rare_term_settings=RareTermPropagationSettings(
                ranking_weight=0.05,
                max_document_frequency=3,
                minimum_supporting_related_pages=2,
            ),
        )[0]

        self.assertGreater(baseline.score_rare_term_propagation, 0.5)
        self.assertEqual(
            len(baseline.rare_term_diagnostics["matched_propagated_terms"]),
            1,
        )
        self.assertAlmostEqual(
            enabled.score_final,
            baseline.score_final + 0.05 * (2 * (baseline.score_rare_term_propagation - 0.5)),
            places=6,
        )


class FieldAwareRelevanceServiceTests(TestCase):
    def test_field_aware_relevance_matches_title_body_and_scope_separately(self):
        destination = ContentRecord(
            content_id=501,
            content_type="thread",
            title="Internal Linking Guide",
            distilled_text="Safe editor workflow for internal links.",
            scope_id=10,
            scope_type="node",
            parent_id=100,
            parent_type="category",
            grandparent_id=1000,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"internal", "linking", "guide"}),
            scope_title="Guides",
            parent_scope_title="SEO",
            grandparent_scope_title="Marketing",
        )

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="This internal linking guide helps editor workflow inside the SEO guides area.",
            inbound_anchor_rows=[
                LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
                LearnedAnchorInputRow(source_content_id=2, anchor_text="Internal Linking Guide"),
            ],
            settings=FieldAwareRelevanceSettings(),
        )

        self.assertGreater(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_state, "computed_match")
        self.assertGreater(result.field_aware_diagnostics["field_scores"]["title"]["score"], 0.0)
        self.assertGreater(result.field_aware_diagnostics["field_scores"]["body"]["score"], 0.0)
        self.assertGreater(result.field_aware_diagnostics["field_scores"]["scope"]["score"], 0.0)

    def test_field_aware_relevance_stays_neutral_without_matches(self):
        destination = _content_record(content_id=502, silo_group_id=None)

        result = evaluate_field_aware_relevance(
            destination=destination,
            host_sentence_text="Completely unrelated sentence about oranges and bicycles.",
            inbound_anchor_rows=[],
            settings=FieldAwareRelevanceSettings(),
        )

        self.assertEqual(result.score_field_aware_relevance, 0.5)
        self.assertEqual(result.field_aware_state, "neutral_no_field_matches")


class FieldAwareRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=601, silo_group_id=None)
        self.host = _content_record(content_id=602, silo_group_id=None)
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)
        self.learned_rows = {
            self.destination.key: [
                LearnedAnchorInputRow(source_content_id=1, anchor_text="Internal Linking Guide"),
                LearnedAnchorInputRow(source_content_id=2, anchor_text="Guide"),
            ]
        }

    def test_field_aware_weight_zero_is_a_ranking_no_op(self):
        destination = ContentRecord(
            content_id=self.destination.content_id,
            content_type=self.destination.content_type,
            title="Internal Linking Guide",
            distilled_text="Internal link guide for editors.",
            scope_id=500,
            scope_type="node",
            parent_id=900,
            parent_type="category",
            grandparent_id=1200,
            grandparent_type="category",
            silo_group_id=None,
            silo_group_name="",
            reply_count=5,
            march_2026_pagerank_score=0.2,
            link_freshness_score=0.5,
            primary_post_char_count=500,
            tokens=frozenset({"guide", "internal", "link"}),
            scope_title="Guides",
            parent_scope_title="SEO",
            grandparent_scope_title="Marketing",
        )
        host = ContentRecord(
            content_id=self.host.content_id,
            content_type=self.host.content_type,
            title=self.host.title,
            distilled_text=self.host.distilled_text,
            scope_id=self.host.scope_id,
            scope_type=self.host.scope_type,
            parent_id=self.host.parent_id,
            parent_type=self.host.parent_type,
            grandparent_id=self.host.grandparent_id,
            grandparent_type=self.host.grandparent_type,
            silo_group_id=self.host.silo_group_id,
            silo_group_name=self.host.silo_group_name,
            reply_count=99,
            march_2026_pagerank_score=1.8,
            link_freshness_score=self.host.link_freshness_score,
            primary_post_char_count=900,
            tokens=frozenset({"guide", "link", "seo", "internal"}),
        )
        sentence_records = {
            60: SentenceRecord(
                60,
                host.content_id,
                host.content_type,
                "This internal linking guide helps SEO editors improve internal links.",
                80,
                frozenset({"internal", "linking", "guide", "seo", "editors", "links"}),
            )
        }

        baseline = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 60, 0.8)],
            content_records={destination.key: destination, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            field_aware_settings=FieldAwareRelevanceSettings(ranking_weight=0.0),
        )[0]
        enabled = score_destination_matches(
            destination,
            [SentenceSemanticMatch(host.content_id, host.content_type, 60, 0.8)],
            content_records={destination.key: destination, host.key: host},
            sentence_records=sentence_records,
            existing_links=set(),
            learned_anchor_rows_by_destination=self.learned_rows,
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            field_aware_settings=FieldAwareRelevanceSettings(ranking_weight=0.05),
        )[0]

        self.assertGreater(baseline.score_field_aware_relevance, 0.5)
        self.assertAlmostEqual(
            enabled.score_final,
            baseline.score_final + 0.05 * (2 * (baseline.score_field_aware_relevance - 0.5)),
            places=6,
        )


class WeightedAuthorityGraphTests(TestCase):
    def setUp(self):
        self.scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")

    def _content(self, content_id: int, title: str) -> ContentItem:
        return ContentItem.objects.create(
            content_id=content_id,
            content_type="thread",
            title=title,
            scope=self.scope,
        )

    def test_uniform_weight_behavior_populates_march_2026_pagerank_score(self):
        a = self._content(1, "A")
        b = self._content(2, "B")
        c = self._content(3, "C")

        ExistingLink.objects.create(
            from_content_item=a,
            to_content_item=b,
            anchor_text="B",
            extraction_method="html_anchor",
            link_ordinal=0,
            source_internal_link_count=2,
            context_class="contextual",
        )
        ExistingLink.objects.create(
            from_content_item=a,
            to_content_item=c,
            anchor_text="C",
            extraction_method="html_anchor",
            link_ordinal=1,
            source_internal_link_count=2,
            context_class="contextual",
        )
        ExistingLink.objects.create(
            from_content_item=b,
            to_content_item=c,
            anchor_text="C",
            extraction_method="html_anchor",
            link_ordinal=0,
            source_internal_link_count=1,
            context_class="contextual",
        )
        ExistingLink.objects.create(
            from_content_item=c,
            to_content_item=a,
            anchor_text="A",
            extraction_method="html_anchor",
            link_ordinal=0,
            source_internal_link_count=1,
            context_class="contextual",
        )

        diagnostics = run_weighted_pagerank(
            settings_map={
                "position_bias": 0.0,
                "empty_anchor_factor": 1.0,
                "bare_url_factor": 1.0,
                "weak_context_factor": 1.0,
                "isolated_context_factor": 1.0,
            }
        )

        march_2026_scores = {
            item.pk: item.march_2026_pagerank_score
            for item in ContentItem.objects.order_by("pk")
        }

        self.assertEqual(diagnostics["fallback_row_count"], 0)
        self.assertTrue(all(score >= 0.0 for score in march_2026_scores.values()))
        self.assertAlmostEqual(sum(march_2026_scores.values()), 1.0, places=6)

    def test_outbound_normalization_boilerplate_downweight_and_contextual_upweight(self):
        probabilities, used_fallback = _normalize_source_edges(
            [
                _WeightedEdge(
                    source_index=0,
                    target_index=1,
                    anchor_text="Editorial link",
                    extraction_method="html_anchor",
                    link_ordinal=0,
                    source_internal_link_count=2,
                    context_class="contextual",
                    pk=1,
                ),
                _WeightedEdge(
                    source_index=0,
                    target_index=2,
                    anchor_text="",
                    extraction_method="bare_url",
                    link_ordinal=1,
                    source_internal_link_count=2,
                    context_class="isolated",
                    pk=2,
                ),
            ],
            settings_map={
                "position_bias": 0.5,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )

        self.assertFalse(used_fallback)
        self.assertGreater(probabilities[0], probabilities[1])
        self.assertAlmostEqual(sum(probabilities), 1.0, places=6)

    def test_monotonicity_improving_context_increases_edge_probability(self):
        baseline_probabilities, _ = _normalize_source_edges(
            [
                _WeightedEdge(0, 1, "A", "html_anchor", 0, 2, "weak_context", 1),
                _WeightedEdge(0, 2, "B", "html_anchor", 1, 2, "contextual", 2),
            ],
            settings_map={
                "position_bias": 0.0,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )
        improved_probabilities, _ = _normalize_source_edges(
            [
                _WeightedEdge(0, 1, "A", "html_anchor", 0, 2, "contextual", 1),
                _WeightedEdge(0, 2, "B", "html_anchor", 1, 2, "contextual", 2),
            ],
            settings_map={
                "position_bias": 0.0,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )

        self.assertGreater(improved_probabilities[0], baseline_probabilities[0])

    def test_missing_feature_rows_fallback_to_neutral_uniform_behavior(self):
        probabilities, used_fallback = _normalize_source_edges(
            [
                _WeightedEdge(0, 1, "First", "", None, None, "", 1),
                _WeightedEdge(0, 2, "Second", "", None, None, "", 2),
            ],
            settings_map={
                "position_bias": 0.5,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )

        self.assertFalse(used_fallback)
        self.assertAlmostEqual(probabilities[0], 0.5, places=6)
        self.assertAlmostEqual(probabilities[1], 0.5, places=6)

    def test_nonfinite_rows_fallback_to_uniform_probabilities(self):
        probabilities, used_fallback = _normalize_source_edges(
            [
                _WeightedEdge(0, 1, "First", "html_anchor", 0, 2, "contextual", 1),
                _WeightedEdge(0, 2, "Second", "html_anchor", 1, 2, "contextual", 2),
            ],
            settings_map={
                "position_bias": math.inf,
                "empty_anchor_factor": 0.6,
                "bare_url_factor": 0.35,
                "weak_context_factor": 0.75,
                "isolated_context_factor": 0.45,
            },
        )

        self.assertTrue(used_fallback)
        self.assertAlmostEqual(probabilities[0], 0.5, places=6)
        self.assertAlmostEqual(probabilities[1], 0.5, places=6)


class ClickDistanceServiceTests(TestCase):
    def test_url_depth_calculation(self):
        service = ClickDistanceService()
        self.assertEqual(service.calculate_url_depth("https://example.com/"), 0)
        self.assertEqual(service.calculate_url_depth("https://example.com/item/"), 1)
        self.assertEqual(service.calculate_url_depth("https://example.com/path/to/item"), 3)
        self.assertEqual(service.calculate_url_depth(""), 0)

    def test_scope_depth_map_building(self):
        root = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Root")
        child = ScopeItem.objects.create(scope_id=2, scope_type="node", title="Child", parent=root)
        grandchild = ScopeItem.objects.create(scope_id=3, scope_type="node", title="Grandchild", parent=child)
        standalone = ScopeItem.objects.create(scope_id=4, scope_type="node", title="Standalone")

        service = ClickDistanceService()
        depth_map = service.build_scope_depth_map()

        self.assertEqual(depth_map[root.id], 0)
        self.assertEqual(depth_map[child.id], 1)
        self.assertEqual(depth_map[grandchild.id], 2)
        self.assertEqual(depth_map[standalone.id], 0)

    def test_score_calculation_logic(self):
        # Default settings: k_cd=4.0, b_cd=0.75, b_ud=0.25
        settings = ClickDistanceSettings(ranking_weight=0.1, k_cd=4.0, b_cd=0.75, b_ud=0.25)
        service = ClickDistanceService(settings=settings)

        # root: depth 0, url 0 -> blended 0.75 / 1.0 = 0.75
        # score = 4 / (4 + 0.75) = 0.842
        score, state, diags = service.calculate_score(scope_depth=0, url_depth=0)
        self.assertEqual(state, "computed")
        self.assertAlmostEqual(score, 0.842105, places=6)

        # deep: depth 4, url 4 -> blended (0.75*5 + 0.25*4) = 4.75
        # score = 4 / (4 + 4.75) = 0.45714...
        score2, _, _ = service.calculate_score(scope_depth=4, url_depth=4)
        self.assertLess(score2, score)
        self.assertAlmostEqual(score2, 0.457143, places=6)

    def test_recalculate_all_updates_content_items(self):
        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        ContentItem.objects.create(content_id=1, content_type="thread", title="P1", scope=scope, url="https://x.com/1")
        ContentItem.objects.create(content_id=2, content_type="thread", title="P2", scope=scope, url="https://x.com/a/b")

        service = ClickDistanceService()
        service.recalculate_all()

        p1 = ContentItem.objects.get(content_id=1)
        p2 = ContentItem.objects.get(content_id=2)
        self.assertGreater(p1.click_distance_score, 0.5)
        self.assertGreater(p1.click_distance_score, p2.click_distance_score)


class ClickDistanceRankerIntegrationTests(TestCase):
    def setUp(self):
        self.destination = _content_record(content_id=10, silo_group_id=None)
        # destination has click_distance_score (the field on ContentItem)
        # In ranker, it's passed via ContentRecord
        self.host = _content_record(content_id=20, silo_group_id=None)
        self.records = {self.destination.key: self.destination, self.host.key: self.host}
        self.weights = {"w_semantic": 0.5, "w_keyword": 0.5, "w_node": 0, "w_quality": 0}
        self.bounds = (0.1, 2.0)

    def test_click_distance_weight_zero_has_no_effect(self):
        dest_neutral = _content_record(content_id=10, silo_group_id=None)
        # click_distance_score defaults to 0.0 in _content_record but 0.5 means neutral in ranker
        
        matches = [SentenceSemanticMatch(20, "thread", 20, 0.8)]
        sentence_records = {20: SentenceRecord(20, 20, "thread", "test", 80, frozenset())}

        baseline = score_destination_matches(
            dest_neutral,
            matches,
            content_records=self.records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            click_distance_ranking_weight=0.0,
        )[0]
        
        enabled = score_destination_matches(
            dest_neutral,
            matches,
            content_records=self.records,
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            click_distance_ranking_weight=0.2,
        )[0]

        self.assertAlmostEqual(baseline.score_final, enabled.score_final, places=6)

    def test_click_distance_score_boosts_final_score(self):
        # Use dataclasses.replace instead of __dict__ for slotted dataclasses
        dest_shallow = replace(self.destination, click_distance_score=0.9)
        dest_deep = replace(self.destination, click_distance_score=0.3)
        
        matches = [SentenceSemanticMatch(20, "thread", 20, 0.8)]
        sentence_records = {20: SentenceRecord(20, 20, "thread", "test", 80, frozenset())}
        
        shallow_result = score_destination_matches(
            dest_shallow,
            matches,
            content_records={dest_shallow.key: dest_shallow, self.host.key: self.host},
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            click_distance_ranking_weight=0.2,
        )[0]
        
        deep_result = score_destination_matches(
            dest_deep,
            matches,
            content_records={dest_deep.key: dest_deep, self.host.key: self.host},
            sentence_records=sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            click_distance_ranking_weight=0.2,
        )[0]

        # score factor = 2 * (score - 0.5)
        # shallow: 2 * (0.9 - 0.5) = 0.8 bonus
        # deep: 2 * (0.3 - 0.5) = -0.4 penalty
        self.assertGreater(shallow_result.score_final, deep_result.score_final)
        self.assertAlmostEqual(shallow_result.score_click_distance, 0.9)
        self.assertAlmostEqual(shallow_result.score_click_distance, 0.9)
        self.assertAlmostEqual(deep_result.score_click_distance, 0.3)


class FeedbackRerankServiceTests(TestCase):
    def setUp(self):
        self.settings = FeedbackRerankSettings(
            enabled=True,
            ranking_weight=0.2,
            exploration_rate=1.0,
            alpha_prior=1.0,
            beta_prior=1.0
        )
        self.service = FeedbackRerankService(self.settings)

    def test_bayesian_smoothing_exploit_score(self):
        # 0/0 -> (0+1)/(0+1+1) = 0.5
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertEqual(diags["score_exploit"], 0.5)
        
        # 10/10 -> (10+1)/(10+2) = 11/12 = 0.9167
        self.service._pair_stats[(1, 1)] = {"total": 10, "successes": 10}
        self.service._global_total_samples = 10
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertAlmostEqual(diags["score_exploit"], 0.9167, places=4)

        # 0/10 -> (0+1)/(10+2) = 1/12 = 0.0833
        self.service._pair_stats[(1, 1)] = {"total": 10, "successes": 0}
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertAlmostEqual(diags["score_exploit"], 0.0833, places=4)

    def test_ucb1_explore_boost(self):
        # Global=100, Pair=0 -> sqrt(ln(101)/1) = 2.14k
        self.service._global_total_samples = 100
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertGreater(diags["score_explore"], 2.0)

        # Global=100, Pair=100 -> sqrt(ln(101)/101) = 0.21k
        self.service._pair_stats[(1, 1)] = {"total": 100, "successes": 50}
        factor, diags = self.service.calculate_rerank_factor(1, 1)
        self.assertLess(diags["score_explore"], 0.3)

    def test_rerank_candidates_integration(self):
        from apps.pipeline.services.ranker import ScoredCandidate
        
        # Mock global stats: a lot of data for (1,1) with 100% success
        self.service._pair_stats[(1, 1)] = {"total": 100, "successes": 100}
        self.service._global_total_samples = 100
        
        candidates = [
            ScoredCandidate(
                destination_content_id=1, destination_content_type="thread",
                host_content_id=2, host_content_type="thread",
                host_sentence_id=1,
                score_semantic=0.8, score_keyword=0.2, score_node_affinity=0.1,
                score_quality=0.5, score_silo_affinity=0.0,
                score_phrase_relevance=0.5, score_learned_anchor_corroboration=0.5,
                score_rare_term_propagation=0.5, score_field_aware_relevance=0.5,
                score_ga4_gsc=0.5, score_click_distance=0.5,
                score_explore_exploit=0.0,
                score_cluster_suppression=0.0, # Added missing field
                score_final=1.0,
                anchor_phrase="test", anchor_start=0, anchor_end=4, anchor_confidence="strong",
                phrase_match_diagnostics={}, learned_anchor_diagnostics={},
                rare_term_diagnostics={}, field_aware_diagnostics={},
                cluster_diagnostics={}, # Added missing field
                explore_exploit_diagnostics={},
                click_distance_diagnostics={}
            )
        ]
        
        # host_id=2 maps to scope=1, dest_id=1 maps to scope=1
        reranked = self.service.rerank_candidates(
            candidates,
            host_scope_id_map={2: 1},
            destination_scope_id_map={1: 1}
        )
        
        # Factor should be > 1.0 because of high success rate
        self.assertGreater(reranked[0].score_final, 1.0)
        self.assertGreater(reranked[0].score_explore_exploit, 1.0)
        self.assertIn("score_exploit", reranked[0].explore_exploit_diagnostics)


class PipelinePersistenceRegressionTests(TestCase):
    def setUp(self):
        self.scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Forum")
        self.run = PipelineRun.objects.create()

        self.destination_a = ContentItem.objects.create(
            content_id=101,
            content_type="thread",
            title="Destination A",
            scope=self.scope,
            march_2026_pagerank_score=0.9,
            velocity_score=0.2,
            link_freshness_score=0.7,
            content_value_score=0.66,
            click_distance_score=0.82,
        )
        self.destination_b = ContentItem.objects.create(
            content_id=102,
            content_type="thread",
            title="Destination B",
            scope=self.scope,
            march_2026_pagerank_score=0.4,
            velocity_score=0.1,
            link_freshness_score=0.6,
            content_value_score=0.58,
            click_distance_score=0.74,
        )
        self.host_a = ContentItem.objects.create(
            content_id=201,
            content_type="thread",
            title="Host A",
            scope=self.scope,
            march_2026_pagerank_score=0.3,
        )
        self.host_b = ContentItem.objects.create(
            content_id=202,
            content_type="thread",
            title="Host B",
            scope=self.scope,
            march_2026_pagerank_score=0.2,
        )
        self.post_a = Post.objects.create(content_item=self.host_a, raw_bbcode="host a", clean_text="host a")
        self.post_b = Post.objects.create(content_item=self.host_b, raw_bbcode="host b", clean_text="host b")
        self.sentence_a = Sentence.objects.create(
            content_item=self.host_a,
            post=self.post_a,
            text="Host sentence A",
            position=0,
            char_count=15,
            start_char=0,
            end_char=15,
            word_position=1,
        )
        self.sentence_b = Sentence.objects.create(
            content_item=self.host_b,
            post=self.post_b,
            text="Host sentence B",
            position=0,
            char_count=15,
            start_char=0,
            end_char=15,
            word_position=1,
        )
        self.content_records = {
            (self.destination_a.pk, self.destination_a.content_type): self._record(self.destination_a),
            (self.destination_b.pk, self.destination_b.content_type): self._record(self.destination_b),
            (self.host_a.pk, self.host_a.content_type): self._record(self.host_a, reply_count=9),
            (self.host_b.pk, self.host_b.content_type): self._record(self.host_b, reply_count=7),
        }
        self.sentence_records = {
            self.sentence_a.pk: SentenceRecord(
                self.sentence_a.pk,
                self.host_a.pk,
                self.host_a.content_type,
                self.sentence_a.text,
                self.sentence_a.char_count,
                frozenset({"host", "a"}),
            ),
            self.sentence_b.pk: SentenceRecord(
                self.sentence_b.pk,
                self.host_b.pk,
                self.host_b.content_type,
                self.sentence_b.text,
                self.sentence_b.char_count,
                frozenset({"host", "b"}),
            ),
        }

    def _record(self, item: ContentItem, *, reply_count: int = 5) -> ContentRecord:
        return ContentRecord(
            content_id=item.pk,
            content_type=item.content_type,
            title=item.title,
            distilled_text=f"{item.title} body",
            scope_id=item.scope_id or 0,
            scope_type=item.scope.scope_type if item.scope else "",
            parent_id=None,
            parent_type="",
            grandparent_id=None,
            grandparent_type="",
            silo_group_id=None,
            silo_group_name="",
            reply_count=reply_count,
            march_2026_pagerank_score=item.march_2026_pagerank_score,
            link_freshness_score=item.link_freshness_score,
            content_value_score=item.content_value_score,
            click_distance_score=item.click_distance_score,
            primary_post_char_count=500,
            tokens=frozenset({item.title.lower(), "guide"}),
            scope_title=item.scope.title if item.scope else "",
        )

    def test_persist_suggestions_saves_real_scores_and_uses_batched_fetches(self):
        candidates = [
            _scored_candidate(
                destination_content_id=self.destination_a.pk,
                host_content_id=self.host_a.pk,
                host_sentence_id=self.sentence_a.pk,
                score_final=1.41,
                score_click_distance=0.82,
                score_explore_exploit=1.25,
                click_distance_diagnostics={"score_component": 0.64, "state": "computed"},
                explore_exploit_diagnostics={"final_factor": 1.25, "n_pair": 5},
            ),
            _scored_candidate(
                destination_content_id=self.destination_b.pk,
                host_content_id=self.host_b.pk,
                host_sentence_id=self.sentence_b.pk,
                score_final=1.19,
                score_click_distance=0.74,
                score_explore_exploit=0.91,
                click_distance_diagnostics={"score_component": 0.48, "state": "computed"},
                explore_exploit_diagnostics={"final_factor": 0.91, "n_pair": 2},
            ),
        ]

        with CaptureQueriesContext(connection) as queries:
            created = _persist_suggestions(
                run_id=str(self.run.run_id),
                selected_candidates=candidates,
                content_records=self.content_records,
                sentence_records=self.sentence_records,
                rerun_mode="skip_pending",
            )

        self.assertEqual(created, 2)
        self.assertLessEqual(len(queries), 4)

        suggestion_a = Suggestion.objects.get(destination=self.destination_a)
        suggestion_b = Suggestion.objects.get(destination=self.destination_b)

        self.assertEqual(suggestion_a.score_click_distance, 0.82)
        self.assertEqual(suggestion_a.score_explore_exploit, 1.25)
        self.assertEqual(suggestion_a.click_distance_diagnostics["state"], "computed")
        self.assertEqual(suggestion_a.explore_exploit_diagnostics["final_factor"], 1.25)
        self.assertEqual(suggestion_a.destination_title, self.destination_a.title)
        self.assertEqual(suggestion_a.host_sentence_text, self.sentence_a.text)

        self.assertEqual(suggestion_b.score_click_distance, 0.74)
        self.assertEqual(suggestion_b.score_explore_exploit, 0.91)
        self.assertEqual(suggestion_b.click_distance_diagnostics["score_component"], 0.48)
        self.assertEqual(suggestion_b.explore_exploit_diagnostics["n_pair"], 2)

    def test_persist_diagnostics_saves_details_with_batched_content_lookup(self):
        with CaptureQueriesContext(connection) as queries:
            _persist_diagnostics(
                run_id=str(self.run.run_id),
                diagnostics=[
                    (self.destination_a.pk, "thread", "no_semantic_matches", {"stage": 2}),
                    (self.destination_b.pk, "thread", "cross_silo_blocked", {"mode": "strict_same_silo"}),
                ],
            )

        self.assertLessEqual(len(queries), 3)
        diagnostics = {
            diagnostic.destination_id: diagnostic
            for diagnostic in PipelineDiagnostic.objects.order_by("destination_id")
        }
        self.assertEqual(diagnostics[self.destination_a.pk].detail["stage"], 2)
        self.assertEqual(diagnostics[self.destination_b.pk].detail["mode"], "strict_same_silo")


class PipelineServiceRegressionTests(TestCase):
    def _build_run_fixtures(self):
        destination_a = _content_record(content_id=101, silo_group_id=10)
        destination_b = _content_record(content_id=102, silo_group_id=20)
        host = _content_record(content_id=201, silo_group_id=10)
        sentence_records = {
            501: SentenceRecord(501, 201, "thread", "Helpful host sentence", 80, frozenset({"helpful"})),
            502: SentenceRecord(502, 201, "thread", "Second host sentence", 80, frozenset({"second"})),
        }
        candidate = _scored_candidate(
            destination_content_id=101,
            host_content_id=201,
            host_sentence_id=501,
            score_final=1.33,
            score_click_distance=0.77,
            score_explore_exploit=1.17,
        )
        content_records = {
            destination_a.key: destination_a,
            destination_b.key: destination_b,
            host.key: host,
        }
        return content_records, sentence_records, candidate

    def test_feedback_rerank_path_uses_destination_content_id_and_no_longer_crashes(self):
        content_records, sentence_records, candidate = self._build_run_fixtures()
        feedback_service = MagicMock()
        feedback_service.load_historical_stats.return_value = None
        feedback_service.rerank_candidates.return_value = [candidate]

        with ExitStack() as stack:
            stack.enter_context(patch.object(pipeline_service, "_load_weights", return_value=dict(DEFAULT_WEIGHTS)))
            stack.enter_context(patch.object(pipeline_service, "_load_silo_settings", return_value=SiloSettings()))
            stack.enter_context(patch.object(pipeline_service, "_load_weighted_authority_settings", return_value={"ranking_weight": 0.0}))
            stack.enter_context(patch.object(pipeline_service, "_load_link_freshness_settings", return_value={"ranking_weight": 0.0}))
            stack.enter_context(patch.object(pipeline_service, "_load_phrase_matching_settings", return_value=PhraseMatchingSettings()))
            stack.enter_context(patch.object(pipeline_service, "_load_learned_anchor_settings", return_value=LearnedAnchorSettings()))
            stack.enter_context(patch.object(pipeline_service, "_load_rare_term_propagation_settings", return_value=RareTermPropagationSettings(enabled=False)))
            stack.enter_context(patch.object(pipeline_service, "_load_field_aware_relevance_settings", return_value=FieldAwareRelevanceSettings()))
            stack.enter_context(patch.object(pipeline_service, "_load_ga4_gsc_settings", return_value={"ranking_weight": 0.0}))
            stack.enter_context(patch.object(pipeline_service, "_load_click_distance_settings", return_value={"ranking_weight": 0.0}))
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_load_feedback_rerank_settings",
                    return_value=FeedbackRerankSettings(enabled=True, ranking_weight=0.2, exploration_rate=1.0),
                )
            )
            stack.enter_context(patch.object(pipeline_service, "_load_clustering_settings", return_value=ClusteringSettings()))
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_load_slate_diversity_settings",
                    return_value=SlateDiversitySettings(enabled=False),
                )
            )
            stack.enter_context(patch.object(pipeline_service, "_get_max_host_reuse", return_value=3))
            stack.enter_context(patch.object(pipeline_service, "FeedbackRerankService", return_value=feedback_service))
            stack.enter_context(patch.object(pipeline_service, "_load_content_records", return_value=content_records))
            stack.enter_context(patch.object(pipeline_service, "_load_sentence_records", return_value=(sentence_records, {})))
            stack.enter_context(patch.object(pipeline_service, "_load_existing_links", return_value=set()))
            stack.enter_context(patch.object(pipeline_service, "_load_learned_anchor_rows_by_destination", return_value={}))
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_load_destination_embeddings",
                    return_value=(((101, "thread"),), np.array([[1.0, 0.0]], dtype=np.float32)),
                )
            )
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_load_sentence_embeddings",
                    return_value=([501], np.array([[1.0, 0.0]], dtype=np.float32)),
                )
            )
            stack.enter_context(patch.object(pipeline_service, "_stage1_candidates", return_value={(101, "thread"): [501]}))
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_score_sentences_stage2",
                    return_value=[SentenceSemanticMatch(201, "thread", 501, 0.9)],
                )
            )
            stack.enter_context(patch.object(pipeline_service, "score_destination_matches", return_value=[candidate]))
            stack.enter_context(patch.object(pipeline_service, "select_final_candidates", return_value=[candidate]))
            stack.enter_context(patch.object(pipeline_service, "_persist_suggestions", return_value=1))
            stack.enter_context(patch.object(pipeline_service, "_persist_diagnostics"))

            result = pipeline_service.run_pipeline(run_id="feedback-run")

        self.assertEqual(result.suggestions_created, 1)
        feedback_service.rerank_candidates.assert_called_once()
        _, kwargs = feedback_service.rerank_candidates.call_args
        self.assertEqual(kwargs["destination_scope_id_map"], {101: content_records[(101, "thread")].scope_id})

    def test_run_pipeline_returns_correct_processed_and_skipped_counts(self):
        content_records, sentence_records, candidate = self._build_run_fixtures()

        with ExitStack() as stack:
            stack.enter_context(patch.object(pipeline_service, "_load_weights", return_value=dict(DEFAULT_WEIGHTS)))
            stack.enter_context(patch.object(pipeline_service, "_load_silo_settings", return_value=SiloSettings()))
            stack.enter_context(patch.object(pipeline_service, "_load_weighted_authority_settings", return_value={"ranking_weight": 0.0}))
            stack.enter_context(patch.object(pipeline_service, "_load_link_freshness_settings", return_value={"ranking_weight": 0.0}))
            stack.enter_context(patch.object(pipeline_service, "_load_phrase_matching_settings", return_value=PhraseMatchingSettings()))
            stack.enter_context(patch.object(pipeline_service, "_load_learned_anchor_settings", return_value=LearnedAnchorSettings()))
            stack.enter_context(patch.object(pipeline_service, "_load_rare_term_propagation_settings", return_value=RareTermPropagationSettings(enabled=False)))
            stack.enter_context(patch.object(pipeline_service, "_load_field_aware_relevance_settings", return_value=FieldAwareRelevanceSettings()))
            stack.enter_context(patch.object(pipeline_service, "_load_ga4_gsc_settings", return_value={"ranking_weight": 0.0}))
            stack.enter_context(patch.object(pipeline_service, "_load_click_distance_settings", return_value={"ranking_weight": 0.0}))
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_load_feedback_rerank_settings",
                    return_value=FeedbackRerankSettings(enabled=False),
                )
            )
            stack.enter_context(patch.object(pipeline_service, "_load_clustering_settings", return_value=ClusteringSettings()))
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_load_slate_diversity_settings",
                    return_value=SlateDiversitySettings(enabled=False),
                )
            )
            stack.enter_context(patch.object(pipeline_service, "_get_max_host_reuse", return_value=3))
            stack.enter_context(patch.object(pipeline_service, "_load_content_records", return_value=content_records))
            stack.enter_context(patch.object(pipeline_service, "_load_sentence_records", return_value=(sentence_records, {})))
            stack.enter_context(patch.object(pipeline_service, "_load_existing_links", return_value=set()))
            stack.enter_context(patch.object(pipeline_service, "_load_learned_anchor_rows_by_destination", return_value={}))
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_load_destination_embeddings",
                    return_value=(
                        ((101, "thread"), (102, "thread")),
                        np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
                    ),
                )
            )
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_load_sentence_embeddings",
                    return_value=(
                        [501, 502],
                        np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
                    ),
                )
            )
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_stage1_candidates",
                    return_value={(101, "thread"): [501], (102, "thread"): [502]},
                )
            )
            stack.enter_context(
                patch.object(
                    pipeline_service,
                    "_score_sentences_stage2",
                    side_effect=[
                        [SentenceSemanticMatch(201, "thread", 501, 0.9)],
                        [],
                    ],
                )
            )
            stack.enter_context(patch.object(pipeline_service, "score_destination_matches", return_value=[candidate]))
            stack.enter_context(patch.object(pipeline_service, "select_final_candidates", return_value=[candidate]))
            stack.enter_context(patch.object(pipeline_service, "_persist_suggestions", return_value=1))
            persist_diagnostics = stack.enter_context(patch.object(pipeline_service, "_persist_diagnostics"))

            result = pipeline_service.run_pipeline(run_id="stats-run")

        self.assertEqual(result.items_in_scope, 2)
        self.assertEqual(result.suggestions_created, 1)
        self.assertEqual(result.destinations_skipped, 1)
        _, kwargs = persist_diagnostics.call_args
        self.assertIn((102, "thread", "no_semantic_matches", None), kwargs["diagnostics"])


class Stage2RegressionTests(TestCase):
    def test_precomputed_lookup_keeps_stage2_results_unchanged(self):
        sentence_records = {
            10: SentenceRecord(10, 110, "thread", "Sentence 10", 20, frozenset({"ten"})),
            20: SentenceRecord(20, 120, "thread", "Sentence 20", 20, frozenset({"twenty"})),
            30: SentenceRecord(30, 130, "thread", "Sentence 30", 20, frozenset({"thirty"})),
            40: SentenceRecord(40, 140, "thread", "Sentence 40", 20, frozenset({"forty"})),
        }
        sentence_ids_ordered = [30, 10, 20, 40]
        sentence_embeddings = np.array(
            [
                [0.2, 0.1],
                [1.0, 0.0],
                [0.8, 0.2],
                [0.6, 0.4],
            ],
            dtype=np.float32,
        )
        lookup = {sentence_id: index for index, sentence_id in enumerate(sentence_ids_ordered)}
        kwargs = {
            "destination_embedding": np.array([1.0, 0.0], dtype=np.float32),
            "sentence_ids": [20, 40, 10, 999],
            "sentence_ids_ordered": sentence_ids_ordered,
            "sentence_embeddings": sentence_embeddings,
            "sentence_records": sentence_records,
            "top_k": 3,
        }

        baseline = _score_sentences_stage2(**kwargs)
        optimized = _score_sentences_stage2(**kwargs, sentence_id_to_row=lookup)

        self.assertEqual(baseline, optimized)
        self.assertEqual([match.sentence_id for match in optimized], [10, 20, 40])
        self.assertAlmostEqual(optimized[0].score_semantic, 1.0)
        self.assertAlmostEqual(optimized[1].score_semantic, 0.8)
        self.assertAlmostEqual(optimized[2].score_semantic, 0.6)


class SlateDiversityServiceTests(TestCase):
    def test_apply_slate_diversity_swaps_in_more_varied_candidate_for_same_host(self):
        host_key = (900, "thread")
        candidates_by_destination = {
            (101, "thread"): [_scored_candidate(destination_content_id=101, host_content_id=900, host_sentence_id=1, score_final=0.95)],
            (102, "thread"): [_scored_candidate(destination_content_id=102, host_content_id=900, host_sentence_id=2, score_final=0.93)],
            (103, "thread"): [_scored_candidate(destination_content_id=103, host_content_id=900, host_sentence_id=3, score_final=0.91)],
        }
        embedding_lookup = {
            (101, "thread"): np.array([1.0, 0.0], dtype=np.float32),
            (102, "thread"): np.array([0.99, 0.01], dtype=np.float32),
            (103, "thread"): np.array([0.0, 1.0], dtype=np.float32),
        }

        selected = apply_slate_diversity(
            candidates_by_destination=candidates_by_destination,
            embedding_lookup=embedding_lookup,
            settings=SlateDiversitySettings(
                enabled=True,
                diversity_lambda=0.65,
                score_window=0.30,
                similarity_cap=0.90,
            ),
            max_per_host=2,
        )

        self.assertEqual(
            [candidate.destination_content_id for candidate in selected],
            [101, 103],
        )
        self.assertEqual(selected[0].slate_diversity_diagnostics["slot"], 0)
        self.assertEqual(selected[1].slate_diversity_diagnostics["slot"], 1)
        self.assertEqual(selected[1].slate_diversity_diagnostics["swapped_from_rank"], 1)
        self.assertFalse(selected[1].slate_diversity_diagnostics["flagged_redundant"])

    def test_apply_slate_diversity_uses_content_key_embedding_lookup(self):
        candidates_by_destination = {
            (101, "thread"): [_scored_candidate(destination_content_id=101, host_content_id=800, host_sentence_id=1, score_final=0.95)],
            (102, "thread"): [_scored_candidate(destination_content_id=102, host_content_id=800, host_sentence_id=2, score_final=0.92)],
        }
        embedding_lookup = {
            (101, "thread"): np.array([1.0, 0.0], dtype=np.float32),
            (102, "thread"): np.array([0.0, 1.0], dtype=np.float32),
        }

        selected = apply_slate_diversity(
            candidates_by_destination=candidates_by_destination,
            embedding_lookup=embedding_lookup,
            settings=SlateDiversitySettings(enabled=True),
            max_per_host=2,
        )

        self.assertEqual(len(selected), 2)
        self.assertIn("runtime_path", selected[0].slate_diversity_diagnostics)
        self.assertIn("runtime_reason", selected[1].slate_diversity_diagnostics)

    def test_slate_diversity_runtime_status_reports_plain_english_reason(self):
        runtime = get_slate_diversity_runtime_status()

        self.assertIn(runtime["path"], {"cpp_extension", "python_fallback"})
        self.assertIsInstance(runtime["reason"], str)
        self.assertTrue(runtime["reason"])


class PipelineTaskRunStatsTests(TestCase):
    def test_task_saves_pipeline_counts_from_service_result(self):
        run = PipelineRun.objects.create()

        with patch.object(
            pipeline_tasks,
            "_publish_progress",
        ), patch(
            "apps.pipeline.services.pipeline.run_pipeline",
            return_value=PipelineResult(
                run_id=str(run.run_id),
                items_in_scope=3,
                suggestions_created=1,
                destinations_skipped=2,
            ),
        ):
            result = pipeline_tasks.run_pipeline.run(
                run_id=str(run.run_id),
                host_scope={},
                destination_scope={},
                rerun_mode="skip_pending",
            )

        run.refresh_from_db()
        self.assertEqual(run.suggestions_created, 1)
        self.assertEqual(run.destinations_processed, 3)
        self.assertEqual(run.destinations_skipped, 2)
        self.assertEqual(result["state"], "completed")


class BrokenLinkScanBenchmarkTests(TestCase):
    @override_settings(
        HTTP_WORKER_ENABLED=False,
        XENFORO_BASE_URL="https://forum.example.com",
    )
    def test_python_broken_link_scan_reports_benchmark_metrics(self):
        if os.environ.get("PIPELINE_RUN_BENCHMARKS") != "1":
            self.skipTest("Set PIPELINE_RUN_BENCHMARKS=1 to run benchmark harness.")

        scope = ScopeItem.objects.create(scope_id=77, scope_type="node", title="Benchmark Scope")
        source = ContentItem.objects.create(
            content_id=7700,
            content_type="thread",
            title="Benchmark Source",
            scope=scope,
        )

        destinations: list[ContentItem] = []
        existing_issues: list[BrokenLink] = []
        for index in range(1000):
            if index < 100:
                url = f"https://forum.example.com/broken/{index}"
            elif index < 200:
                url = f"https://forum.example.com/redirect/{index}"
            elif index < 300:
                url = f"https://forum.example.com/fixed/{index}"
            else:
                url = f"https://forum.example.com/ok/{index}"

            destinations.append(
                ContentItem(
                    content_id=20_000 + index,
                    content_type="thread",
                    title=f"Destination {index}",
                    scope=scope,
                    url=url,
                )
            )

        created_destinations = ContentItem.objects.bulk_create(destinations)
        ExistingLink.objects.bulk_create(
            [
                ExistingLink(
                    from_content_item=source,
                    to_content_item=destination,
                    anchor_text="bench",
                    extraction_method="html_anchor",
                    link_ordinal=index,
                    source_internal_link_count=1,
                    context_class="contextual",
                )
                for index, destination in enumerate(created_destinations)
            ]
        )

        for destination in created_destinations[200:300]:
            existing_issues.append(
                BrokenLink(
                    source_content=source,
                    url=destination.url,
                    http_status=404,
                    status=BrokenLink.STATUS_OPEN,
                    notes="benchmark existing issue",
                )
            )
        BrokenLink.objects.bulk_create(existing_issues)

        def _benchmark_probe(_session, url: str) -> tuple[int, str]:
            if "/broken/" in url:
                return 404, ""
            if "/redirect/" in url:
                return 301, url.replace("/redirect/", "/redirected/")
            return 200, ""

        started_at = perf_counter()
        with patch.object(pipeline_tasks, "_publish_progress"), patch.object(
            pipeline_tasks,
            "_probe_link_health",
            side_effect=_benchmark_probe,
        ), patch("apps.pipeline.tasks.time.sleep"):
            result = pipeline_tasks.scan_broken_links.run(job_id="benchmark-python-broken-links")
        wall_time_ms = round((perf_counter() - started_at) * 1000, 2)
        peak_working_set_bytes = _peak_working_set_bytes()

        metrics = {
            "lane": "broken_link_scan",
            "owner": "python_celery_baseline",
            "dataset_size": 1000,
            "wall_time_ms": wall_time_ms,
            "peak_working_set_bytes": peak_working_set_bytes or None,
            "memory_note": (
                "Use an external parent-process sampler on Windows when peak_working_set_bytes is null."
                if peak_working_set_bytes <= 0
                else ""
            ),
            "throughput_urls_per_second": round(1000 / max(wall_time_ms / 1000, 0.001), 2),
            "scanned_urls": result["scanned_urls"],
            "flagged_urls": result["flagged_urls"],
            "fixed_urls": result["fixed_urls"],
        }
        print(f"BROKEN_LINK_BENCHMARK_JSON:{json.dumps(metrics, sort_keys=True)}")

        self.assertEqual(result["scanned_urls"], 1000)
        self.assertEqual(result["flagged_urls"], 200)
        self.assertEqual(result["fixed_urls"], 100)


class BrokenLinkScanTaskRegressionTests(TestCase):
    def setUp(self):
        self.scope = ScopeItem.objects.create(scope_id=5, scope_type="node", title="Forum")
        self.source = ContentItem.objects.create(content_id=50, content_type="thread", title="Source", scope=self.scope)

    def _existing_link(self, *, url: str) -> ContentItem:
        destination = ContentItem.objects.create(
            content_id=60 + ContentItem.objects.count(),
            content_type="thread",
            title=f"Destination {ContentItem.objects.count()}",
            scope=self.scope,
            url=url,
        )
        ExistingLink.objects.create(
            from_content_item=self.source,
            to_content_item=destination,
            anchor_text="link",
            extraction_method="html_anchor",
            link_ordinal=0,
            source_internal_link_count=1,
            context_class="contextual",
        )
        return destination

    def test_scan_marks_new_issue_as_open(self):
        destination = self._existing_link(url="https://example.com/broken")

        with patch.object(pipeline_tasks, "_publish_progress"), patch.object(
            pipeline_tasks,
            "_probe_link_health",
            return_value=(404, ""),
        ), patch("apps.pipeline.tasks.time.sleep"):
            result = pipeline_tasks.scan_broken_links.run(job_id="scan-open")

        record = BrokenLink.objects.get(source_content=self.source, url=destination.url)
        self.assertEqual(result["flagged_urls"], 1)
        self.assertEqual(result["fixed_urls"], 0)
        self.assertEqual(record.status, BrokenLink.STATUS_OPEN)
        self.assertEqual(record.http_status, 404)

    def test_scan_marks_existing_issue_as_fixed_when_url_recovers(self):
        destination = self._existing_link(url="https://example.com/fixed")
        BrokenLink.objects.create(
            source_content=self.source,
            url=destination.url,
            http_status=404,
            status=BrokenLink.STATUS_OPEN,
            notes="keep me",
        )

        with patch.object(pipeline_tasks, "_publish_progress"), patch.object(
            pipeline_tasks,
            "_probe_link_health",
            return_value=(200, ""),
        ), patch("apps.pipeline.tasks.time.sleep"):
            result = pipeline_tasks.scan_broken_links.run(job_id="scan-fixed")

        record = BrokenLink.objects.get(source_content=self.source, url=destination.url)
        self.assertEqual(result["flagged_urls"], 0)
        self.assertEqual(result["fixed_urls"], 1)
        self.assertEqual(record.status, BrokenLink.STATUS_FIXED)
        self.assertEqual(record.notes, "keep me")

    def test_scan_preserves_ignored_status_for_known_issue(self):
        destination = self._existing_link(url="https://example.com/ignored")
        BrokenLink.objects.create(
            source_content=self.source,
            url=destination.url,
            http_status=301,
            status=BrokenLink.STATUS_IGNORED,
            notes="reviewer kept this ignored",
        )

        with patch.object(pipeline_tasks, "_publish_progress"), patch.object(
            pipeline_tasks,
            "_probe_link_health",
            return_value=(301, "https://example.com/new-home"),
        ), patch("apps.pipeline.tasks.time.sleep"):
            result = pipeline_tasks.scan_broken_links.run(job_id="scan-ignored")

        record = BrokenLink.objects.get(source_content=self.source, url=destination.url)
        self.assertEqual(result["flagged_urls"], 1)
        self.assertEqual(record.status, BrokenLink.STATUS_IGNORED)
        self.assertEqual(record.redirect_url, "https://example.com/new-home")
        self.assertEqual(record.notes, "reviewer kept this ignored")

    def test_scan_returns_cleanly_when_no_urls_exist(self):
        with patch.object(pipeline_tasks, "_publish_progress"), patch.object(
            pipeline_tasks,
            "_probe_link_health",
        ) as probe_health:
            result = pipeline_tasks.scan_broken_links.run(job_id="scan-empty")

        self.assertEqual(result["scanned_urls"], 0)
        self.assertEqual(result["flagged_urls"], 0)
        self.assertEqual(result["fixed_urls"], 0)
        probe_health.assert_not_called()

    @override_settings(
        HTTP_WORKER_ENABLED=True,
        HTTP_WORKER_URL="http://http-worker-api:8080",
        HTTP_WORKER_BROKEN_LINK_BATCH_SIZE=100,
    )
    def test_scan_uses_http_worker_when_enabled(self):
        destination = self._existing_link(url="https://example.com/http-worker")

        with patch.object(pipeline_tasks, "_publish_progress"), patch(
            "apps.graph.services.http_worker_client.check_broken_links",
            return_value=[
                {
                    "source_content_id": self.source.pk,
                    "url": destination.url,
                    "http_status": 404,
                    "redirect_url": "",
                }
            ],
        ) as check_broken_links, patch.object(pipeline_tasks, "_probe_link_health") as probe_health:
            result = pipeline_tasks.scan_broken_links.run(job_id="scan-http-worker")

        record = BrokenLink.objects.get(source_content=self.source, url=destination.url)
        self.assertEqual(result["probe_backend"], "csharp_http_worker")
        self.assertIsNone(result["http_worker_error"])
        self.assertEqual(result["flagged_urls"], 1)
        self.assertEqual(record.status, BrokenLink.STATUS_OPEN)
        check_broken_links.assert_called_once()
        probe_health.assert_not_called()

    @override_settings(
        HTTP_WORKER_ENABLED=True,
        HTTP_WORKER_URL="http://http-worker-api:8080",
    )
    def test_scan_falls_back_to_python_when_http_worker_fails(self):
        destination = self._existing_link(url="https://example.com/http-worker-fallback")

        with patch.object(pipeline_tasks, "_publish_progress"), patch(
            "apps.graph.services.http_worker_client.check_broken_links",
            side_effect=RuntimeError("worker offline"),
        ), patch.object(
            pipeline_tasks,
            "_probe_link_health",
            return_value=(404, ""),
        ) as probe_health, patch("apps.pipeline.tasks.time.sleep"):
            result = pipeline_tasks.scan_broken_links.run(job_id="scan-http-worker-fallback")

        record = BrokenLink.objects.get(source_content=self.source, url=destination.url)
        self.assertEqual(result["probe_backend"], "python_requests_fallback")
        self.assertEqual(result["http_worker_error"], "worker offline")
        self.assertEqual(result["flagged_urls"], 1)
        self.assertEqual(record.status, BrokenLink.STATUS_OPEN)
        probe_health.assert_called_once_with(ANY, destination.url)


class BrokenLinkScanDispatchTests(TestCase):
    @override_settings(
        HEAVY_RUNTIME_OWNER="celery",
        RUNTIME_OWNER_BROKEN_LINK_SCAN="csharp",
        HTTP_WORKER_ENABLED=True,
        XENFORO_BASE_URL="https://forum.example.com",
        WORDPRESS_BASE_URL="https://content.example.com",
        HTTP_WORKER_BROKEN_LINK_BATCH_SIZE=200,
        HTTP_WORKER_BROKEN_LINK_MAX_CONCURRENCY=40,
    )
    def test_dispatch_broken_link_scan_queues_csharp_job_when_owner_is_csharp(self):
        with patch("apps.graph.services.http_worker_client.queue_job") as queue_job, patch.object(
            pipeline_tasks.scan_broken_links,
            "delay",
        ) as delay_task:
            result = pipeline_tasks.dispatch_broken_link_scan(job_id="job-123")

        self.assertEqual(result["runtime_owner"], "csharp")
        queue_job.assert_called_once_with(
            job_id="job-123",
            job_type="broken_link_scan",
            payload={
                "allowed_domains": ["forum.example.com", "content.example.com"],
                "scan_cap": 10_000,
                "batch_size": 200,
                "timeout_seconds": 10,
                "max_concurrency": 40,
                "user_agent": "XF Internal Linker V2 Broken Link Scanner",
            },
        )
        delay_task.assert_not_called()

    @override_settings(
        HEAVY_RUNTIME_OWNER="celery",
        RUNTIME_OWNER_BROKEN_LINK_SCAN="celery",
    )
    def test_dispatch_broken_link_scan_queues_celery_task_when_owner_is_celery(self):
        with patch("apps.graph.services.http_worker_client.queue_job") as queue_job, patch.object(
            pipeline_tasks.scan_broken_links,
            "delay",
        ) as delay_task:
            result = pipeline_tasks.dispatch_broken_link_scan(job_id="job-456")

        self.assertEqual(result["runtime_owner"], "celery")
        delay_task.assert_called_once_with(job_id="job-456")
        queue_job.assert_not_called()


class HeavyRuntimeDispatchGuardrailTests(TestCase):
    @override_settings(
        HEAVY_RUNTIME_OWNER="celery",
        RUNTIME_OWNER_IMPORT="csharp",
    )
    def test_dispatch_import_content_refuses_fake_csharp_ownership(self):
        with self.assertRaisesMessage(RuntimeError, "does not have a real C# import owner yet"):
            pipeline_tasks.dispatch_import_content(mode="full", source="api", job_id="11111111-1111-1111-1111-111111111111")

    @override_settings(
        HEAVY_RUNTIME_OWNER="celery",
        RUNTIME_OWNER_PIPELINE="csharp",
    )
    def test_dispatch_pipeline_run_refuses_fake_csharp_ownership(self):
        with self.assertRaisesMessage(RuntimeError, "does not have a real C# pipeline owner yet"):
            pipeline_tasks.dispatch_pipeline_run(
                run_id="11111111-1111-1111-1111-111111111111",
                host_scope={},
                destination_scope={},
                rerun_mode="skip_pending",
            )


class PipelineSettingsFallbackLoggingTests(TestCase):
    def test_load_weights_logs_and_keeps_default_fallback(self):
        with patch("apps.core.models.AppSetting.objects.filter", side_effect=RuntimeError("boom")), patch.object(
            pipeline_service.logger,
            "exception",
        ) as log_exception:
            weights = _load_weights()

        self.assertEqual(weights, DEFAULT_WEIGHTS)
        log_exception.assert_called_once()
