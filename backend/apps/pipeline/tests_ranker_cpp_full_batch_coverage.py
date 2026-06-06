"""Coverage for the C++ full-batch scoring path in ``ranker.py``.

Phase 2.14 fix: the module flag ``HAS_CPP_FULL_BATCH`` historically probed
``scoring.score_full_batch`` — a name the compiled C++ extension never
exported — so the flag was permanently ``False`` and the ranker silently fell
through to the slow pure-Python ``_calculate_composite_scores_full_batch_py``
even on machines where the kernel loaded fine. The fix probes the real export
``calculate_composite_scores_full_batch`` and calls it at the batch site
inside :func:`score_destination_matches`.

These ``SimpleTestCase`` tests pin that fix:

* ``HAS_CPP_FULL_BATCH`` is now ``True`` in the quality image (the kernel is
  compiled), which would be ``False`` on the pre-change code.
* The C++ batch call site (the ``calculate_composite_scores_full_batch``
  branch) returns the same composite ``score_final`` as the pure-Python
  reference, proving the renamed call is wired correctly and is not a no-op.

``score_destination_matches`` is documented as pure-Python with only a
best-effort, try/except-guarded ContentItem/Sentence prefetch, so these tests
run without a database: the prefetch raises, is caught, logs a neutral-fallback
warning, and scoring proceeds.
"""

from __future__ import annotations

import builtins
import importlib
import warnings
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.pipeline.services import ranker as ranker_service
from apps.pipeline.services.ranker import (
    ContentRecord,
    SentenceRecord,
    SentenceSemanticMatch,
    SiloSettings,
    score_destination_matches,
)


def _content_record(*, content_id: int, silo_group_id: int | None) -> ContentRecord:
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
        march_2026_pagerank_score=0.0,
        link_freshness_score=0.5,
        content_value_score=0.0,
        primary_post_char_count=500,
        tokens=frozenset({"topic", str(content_id)}),
    )


class CppFullBatchScoringPathTests(SimpleTestCase):
    """The renamed C++ batch call must activate and match the Python reference."""

    def setUp(self) -> None:
        self.destination = _content_record(content_id=1, silo_group_id=10)
        self.host = _content_record(content_id=2, silo_group_id=10)
        self.sentence_records = {
            20: SentenceRecord(
                20, 2, "thread", "Useful same silo sentence", 80, frozenset({"topic"})
            ),
        }
        self.match = [SentenceSemanticMatch(2, "thread", 20, 0.8)]
        self.records = {
            self.destination.key: self.destination,
            self.host.key: self.host,
        }
        self.weights = {
            "w_semantic": 0.55,
            "w_keyword": 0.20,
            "w_node": 0.10,
            "w_quality": 0.15,
        }
        self.bounds = (0.1, 2.0)

    def _score(self) -> list:
        return score_destination_matches(
            self.destination,
            self.match,
            content_records=self.records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.bounds,
            silo_settings=SiloSettings(mode="disabled"),
        )

    def test_cpp_full_batch_flag_is_enabled_in_quality_image(self) -> None:
        # Pre-change code probed the non-existent ``score_full_batch`` export,
        # so this flag was permanently False. The fix probes the real export.
        self.assertTrue(
            ranker_service.HAS_CPP_FULL_BATCH,
            "The compiled C++ kernel exports calculate_composite_scores_full_batch, "
            "so the batch flag must be True after the Phase 2.14 rename fix.",
        )
        self.assertTrue(
            hasattr(ranker_service.scoring, "calculate_composite_scores_full_batch")
        )
        self.assertFalse(hasattr(ranker_service.scoring, "score_full_batch"))

    def test_cpp_batch_path_returns_scored_candidate(self) -> None:
        # Exercises the ``calculate_composite_scores_full_batch`` call site
        # (the True branch of ``if HAS_CPP_FULL_BATCH``) end to end.
        results = self._score()
        self.assertEqual(len(results), 1)
        candidate = results[0]
        self.assertEqual(candidate.destination_content_id, 1)
        self.assertEqual(candidate.host_content_id, 2)
        # The composite must be a real finite score, not the empty/zero sentinel.
        self.assertIsInstance(candidate.score_final, float)
        self.assertGreater(candidate.score_final, 0.0)

    def test_cpp_batch_and_python_reference_agree(self) -> None:
        # Force the C++ branch (line 759) then force the Python fallback branch
        # and assert the composite scores agree. This proves the renamed C++
        # call is correctly wired and is not silently returning a wrong value.
        with patch.object(ranker_service, "HAS_CPP_FULL_BATCH", True):
            cpp_score = self._score()[0].score_final
        with patch.object(ranker_service, "HAS_CPP_FULL_BATCH", False):
            py_score = self._score()[0].score_final
        self.assertAlmostEqual(cpp_score, py_score, places=4)


class CppImportFallbackErrorLogTests(SimpleTestCase):
    """When the C++ scoring import fails AND the ErrorLog write also fails,
    the module's best-effort handler must swallow the second failure and log
    it at debug level instead of letting it crash module import.

    Pre-change this branch was a bare ``pass``; the fix logs the secondary
    failure with ``logger.debug(..., exc_info=True)``. The test reloads the
    module with the C++ extension import forced to fail and the ErrorLog write
    forced to raise, then proves the reload still completes (the secondary
    failure was caught) with the Python-fallback flags set.
    """

    def _reload_clean(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            importlib.reload(ranker_service)

    def test_secondary_errorlog_failure_is_swallowed_during_import(self) -> None:
        # Guarantee the module is reloaded back to its real (C++-enabled)
        # state no matter how this test exits, so later tests are unaffected.
        self.addCleanup(self._reload_clean)

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            fromlist = args[2] if len(args) >= 3 else kwargs.get("fromlist")
            if name == "extensions" and fromlist and "scoring" in fromlist:
                raise ImportError("forced: scoring extension missing")
            if name == "extensions.scoring":
                raise ImportError("forced: scoring extension missing")
            return real_import(name, *args, **kwargs)

        with patch("apps.audit.models.ErrorLog.objects") as mock_objs:
            mock_objs.create.side_effect = RuntimeError("ErrorLog table missing")
            with patch.object(builtins, "__import__", side_effect=fake_import):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    importlib.reload(ranker_service)

            # The reload completed without raising, which proves the inner
            # ``except Exception`` swallowed the ErrorLog RuntimeError.
            self.assertFalse(ranker_service.HAS_CPP_EXT)
            self.assertFalse(ranker_service.HAS_CPP_FULL_BATCH)
            # The secondary ErrorLog write was attempted (and raised).
            mock_objs.create.assert_called_once()
