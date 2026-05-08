"""Unit tests for `apps.pipeline.services.monthly_picker`.

KISS: pure-function tests on hand-built `Candidate` lists. No DB, no
fixtures — runs in `SimpleTestCase` so the suite stays fast and there's
no docker dependency.

Covers:
- editorial rules: per-source cap, per-anchor cap, score floor, freshness
- markdown report rendering shape
- strategy_router branches (claude_code / python / env override)
"""

from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.pipeline.services import strategy_router
from apps.pipeline.services.monthly_picker import (
    Candidate,
    pick_top,
    render_markdown_report,
)


def _candidate(
    *,
    suggestion_id: str,
    score: float,
    source: str = "thread-1",
    anchor: str = "default anchor",
    age_days: int = 30,
    cluster: str = "general",
) -> Candidate:
    return Candidate(
        suggestion_id=suggestion_id,
        composite_score=score,
        source_thread_id=source,
        anchor_phrase=anchor,
        source_post_age_days=age_days,
        source_title=f"Source {suggestion_id}",
        target_title=f"Target {suggestion_id}",
        target_url=f"https://example.test/{suggestion_id}",
        cluster_label=cluster,
    )


class EditorialRulesTests(SimpleTestCase):
    """Rules: per-source cap, per-anchor cap, score floor, freshness, limit."""

    def test_score_floor_drops_below_threshold(self) -> None:
        cands = [
            _candidate(suggestion_id="a", score=0.90),
            _candidate(suggestion_id="b", score=0.65),  # below 0.70 floor
            _candidate(suggestion_id="c", score=0.75),
        ]
        picks = pick_top(cands, limit=10, score_floor=0.70)
        ids = [p.candidate.suggestion_id for p in picks]
        self.assertEqual(ids, ["a", "c"])  # b dropped

    def test_per_source_cap_max_three(self) -> None:
        cands = [
            _candidate(
                suggestion_id=str(i), score=0.9, source="thread-X", anchor=f"a{i}"
            )
            for i in range(5)
        ]
        picks = pick_top(cands, limit=10, per_source_cap=3)
        self.assertEqual(len(picks), 3)
        self.assertTrue(all(p.candidate.source_thread_id == "thread-X" for p in picks))

    def test_per_anchor_cap_max_two(self) -> None:
        cands = [
            _candidate(
                suggestion_id=str(i),
                score=0.9,
                source=f"t{i}",
                anchor="shared anchor",
            )
            for i in range(5)
        ]
        picks = pick_top(cands, limit=10, per_anchor_cap=2)
        self.assertEqual(len(picks), 2)

    def test_anchor_normalisation_case_and_whitespace(self) -> None:
        cands = [
            _candidate(suggestion_id="a", score=0.9, source="t1", anchor="Foo Bar"),
            _candidate(suggestion_id="b", score=0.9, source="t2", anchor="  foo bar  "),
            _candidate(suggestion_id="c", score=0.9, source="t3", anchor="FOO BAR"),
        ]
        picks = pick_top(cands, limit=10, per_anchor_cap=2)
        # Three rows but they all share an anchor (after lowercase + strip).
        self.assertEqual(len(picks), 2)

    def test_limit_caps_total_picks(self) -> None:
        cands = [
            _candidate(suggestion_id=str(i), score=0.9, source=f"t{i}", anchor=f"a{i}")
            for i in range(100)
        ]
        picks = pick_top(cands, limit=50)
        self.assertEqual(len(picks), 50)

    def test_freshness_breaks_score_ties(self) -> None:
        cands = [
            _candidate(suggestion_id="old", score=0.80, age_days=200),
            _candidate(suggestion_id="fresh", score=0.80, age_days=10),
        ]
        picks = pick_top(cands, limit=2, freshness_days=90)
        self.assertEqual(picks[0].candidate.suggestion_id, "fresh")
        self.assertEqual(picks[1].candidate.suggestion_id, "old")

    def test_pure_score_order_when_no_ties(self) -> None:
        cands = [
            _candidate(suggestion_id="lo", score=0.71, source="t1", anchor="a1"),
            _candidate(suggestion_id="hi", score=0.99, source="t2", anchor="a2"),
            _candidate(suggestion_id="md", score=0.85, source="t3", anchor="a3"),
        ]
        picks = pick_top(cands, limit=3)
        self.assertEqual(
            [p.candidate.suggestion_id for p in picks],
            ["hi", "md", "lo"],
        )


class MarkdownReportTests(SimpleTestCase):
    def test_empty_picks_renders_helpful_placeholder(self) -> None:
        body = render_markdown_report("2026-05", [])
        self.assertIn("Monthly link suggestions — 2026-05", body)
        self.assertIn("No picks this month", body)

    def test_picks_grouped_by_cluster(self) -> None:
        cands = [
            _candidate(
                suggestion_id="a", score=0.9, source="t1", anchor="a1", cluster="alpha"
            ),
            _candidate(
                suggestion_id="b", score=0.85, source="t2", anchor="a2", cluster="alpha"
            ),
            _candidate(
                suggestion_id="c", score=0.80, source="t3", anchor="a3", cluster="beta"
            ),
        ]
        picks = pick_top(cands, limit=10)
        body = render_markdown_report("2026-05", picks)
        self.assertIn("## alpha", body)
        self.assertIn("## beta", body)
        self.assertIn("**Source a**", body)
        self.assertIn("Anchor: `a1`", body)


class StrategyRouterTests(SimpleTestCase):
    def setUp(self) -> None:
        # Reset cache + env between tests so each branch is exercised cleanly.
        strategy_router.reset_cache()
        self._old_env = os.environ.pop("MONTHLY_STRATEGY", None)

    def tearDown(self) -> None:
        if self._old_env is not None:
            os.environ["MONTHLY_STRATEGY"] = self._old_env
        else:
            os.environ.pop("MONTHLY_STRATEGY", None)
        strategy_router.reset_cache()

    def test_env_override_python(self) -> None:
        os.environ["MONTHLY_STRATEGY"] = "python"
        self.assertEqual(strategy_router.pick_strategy(), "python")

    def test_env_override_claude_code(self) -> None:
        os.environ["MONTHLY_STRATEGY"] = "claude_code"
        self.assertEqual(strategy_router.pick_strategy(), "claude_code")

    def test_explicit_override_arg_beats_env(self) -> None:
        os.environ["MONTHLY_STRATEGY"] = "claude_code"
        self.assertEqual(strategy_router.pick_strategy(override="python"), "python")

    def test_subprocess_success_returns_claude_code(self) -> None:
        class _Result:
            returncode = 0
            stdout = "pong"
            stderr = ""

        with patch(
            "apps.pipeline.services.strategy_router.subprocess.run",
            return_value=_Result(),
        ):
            self.assertEqual(strategy_router.pick_strategy(), "claude_code")

    def test_subprocess_nonzero_returns_python(self) -> None:
        class _Result:
            returncode = 1
            stdout = ""
            stderr = "error"

        with patch(
            "apps.pipeline.services.strategy_router.subprocess.run",
            return_value=_Result(),
        ):
            self.assertEqual(strategy_router.pick_strategy(), "python")

    def test_subprocess_filenotfound_returns_python(self) -> None:
        with patch(
            "apps.pipeline.services.strategy_router.subprocess.run",
            side_effect=FileNotFoundError("claude not on PATH"),
        ):
            self.assertEqual(strategy_router.pick_strategy(), "python")
