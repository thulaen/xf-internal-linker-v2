"""Convention-named SimpleTestCase coverage for apps/ops_feed/tasks.py.

This module runs the bullboard -> Channels bridge: a Celery task that opens a
long-lived gRPC ``Subscribe`` stream and an infinite ``while True`` re-enqueue
loop. NONE of that may run under the mutation gate or it would hang for the
whole task time limit (600 s+) on every mutant.

The hang-safe strategy:

* ``run_bullboard_bridge`` (the infinite-loop entry point) is NEVER invoked. Its
  Celery time-limit literals are pinned with ``assertEqual`` so the mutation gate
  cannot keep a ``+1`` literal mutant alive.
* ``_run_bridge_once`` is exercised ONLY through its dependency-import barrier:
  the lazy ``apps.diagnostics._sidecars...`` import is forced to raise, so the
  function returns its early counter dict immediately — no coordd lock, no gRPC
  Subscribe stream, no broadcast, no network call.
* The module-level tuning constants are pinned exactly so a mutated literal
  (e.g. backoff doubling or the leader-lock hold) is killed on the changed line.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase


class TaskTimeLimitTests(SimpleTestCase):
    def test_run_bullboard_bridge_time_limits(self) -> None:
        from apps.ops_feed.tasks import _TASK_SOFT_TIME_LIMIT, run_bullboard_bridge

        # soft = _TASK_SOFT_TIME_LIMIT (600), hard = soft + 30 (630). Exact match
        # so a literal-increment mutant on either side dies here.
        self.assertEqual(run_bullboard_bridge.soft_time_limit, 600)
        self.assertEqual(run_bullboard_bridge.time_limit, _TASK_SOFT_TIME_LIMIT + 30)
        self.assertEqual(run_bullboard_bridge.time_limit, 630)


class TuningConstantTests(SimpleTestCase):
    def test_backoff_and_lock_constants_are_exact(self) -> None:
        from apps.ops_feed import tasks

        # assertEqual on each literal kills the mutation gate's +1/-1 mutants.
        self.assertEqual(tasks._BACKOFF_INITIAL, 2.0)
        self.assertEqual(tasks._BACKOFF_MAX, 30.0)
        self.assertEqual(tasks._LEADER_LOCK_HOLD_SECONDS, 30)
        self.assertEqual(tasks._TASK_SOFT_TIME_LIMIT, 600)


class RunBridgeOnceDepBarrierTests(SimpleTestCase):
    """When the sidecar deps cannot import, one cycle returns immediately."""

    def test_missing_deps_returns_error_counter_without_network(self) -> None:
        from apps.ops_feed import tasks

        # Force the lazy ``from apps.diagnostics._sidecars.coordd_client import
        # CoorddClient`` to raise ImportError by nulling the module in sys.modules.
        # The import barrier (try/except around the imports) catches it and returns
        # the early counter dict BEFORE any coordd lock, gRPC Subscribe stream, or
        # broadcast can run — so no network call ever happens.
        with patch.dict(
            "sys.modules",
            {"apps.diagnostics._sidecars.coordd_client": None},
        ):
            stats = tasks._run_bridge_once(max_iterations=1)

        # Exact dict: errors incremented to exactly 1, every other counter at 0.
        self.assertEqual(
            stats,
            {"received": 0, "broadcast": 0, "errors": 1, "skipped_not_leader": 0},
        )


class SeverityNameTests(SimpleTestCase):
    """_severity_name falls back to the SEV_<int> form when stubs are absent."""

    def test_fallback_format_when_stub_import_fails(self) -> None:
        from apps.ops_feed import tasks

        with patch.dict("sys.modules", {"apps._sidecars_pb.bullboard": None}):
            # A missing stub module makes the lazy import raise, so the fallback
            # branch returns the exact "SEV_<value>" string.
            self.assertEqual(tasks._severity_name(3), "SEV_3")

    def test_fallback_format_for_zero_pins_the_literal_prefix(self) -> None:
        from apps.ops_feed import tasks

        with patch.dict("sys.modules", {"apps._sidecars_pb.bullboard": None}):
            # Exact string for value 0 pins the "SEV_" literal so a mutmut
            # string-wrap on the f-string prefix is killed; also proves the
            # interpolated value is the argument, not a constant.
            self.assertEqual(tasks._severity_name(0), "SEV_0")


class HelperConstraintMetadataTests(SimpleTestCase):
    """The ``@HelperConstraint`` decorator stamps routing metadata onto the
    bridge task so the helper-routing engine can read its resource profile.

    The decorator sits INSIDE ``@shared_task``, so the metadata lives on the
    Celery task's underlying callable (``run_bullboard_bridge.run`` when the
    task is registered, or ``__wrapped__`` for the raw function). We read it
    via the canonical accessor ``get_constraint`` to prove the exact values
    declared in the source are the values the router will see.
    """

    def test_run_bullboard_bridge_carries_helper_constraint(self) -> None:
        from apps.core.helpers import get_constraint
        from apps.ops_feed.tasks import run_bullboard_bridge

        # The decorator stashes ``__helper_constraint__`` on the wrapped
        # callable; ``get_constraint`` returns it (or None when absent).
        wrapped = getattr(run_bullboard_bridge, "__wrapped__", run_bullboard_bridge)
        meta = get_constraint(wrapped)

        self.assertIsNotNone(
            meta,
            msg="run_bullboard_bridge must declare a @HelperConstraint so the "
            "routing engine knows its resource profile.",
        )
        # Exact values pin the changed decorator lines: a read-only bridge that
        # is not CPU- or GPU-heavy, ~256 MB RAM, ~600 s expected runtime.
        self.assertFalse(meta.cpu_intensive)
        self.assertFalse(meta.gpu_required)
        self.assertEqual(meta.storage_writes_to, "none")
        self.assertEqual(meta.ram_peak_mb, 256)
        self.assertEqual(meta.expected_seconds_p50, 600)


class RunBullboardBridgeBackoffTests(SimpleTestCase):
    """The Celery entry point is hang-safe ONLY with ``max_iterations`` set.

    With ``max_iterations=1`` the ``while True`` loop runs exactly one cycle and
    returns BEFORE ``time.sleep`` — so the backoff branch can be exercised
    without the 600 s task time limit. The dep-import barrier makes the inner
    cycle return its early counter dict with ``received == 0``, which forces the
    grow-backoff branch (``received > 0`` is False).
    """

    def test_single_iteration_returns_inner_stats_without_sleeping(self) -> None:
        from apps.ops_feed import tasks

        # If time.sleep were reached the test would block; patching it to raise
        # proves the ``max_iterations`` early-return path runs first.
        def _explode(_seconds: float) -> None:  # pragma: no cover - must not run
            raise AssertionError("time.sleep must not be called for max_iterations")

        with patch.dict(
            "sys.modules",
            {"apps.diagnostics._sidecars.coordd_client": None},
        ), patch.object(tasks.time, "sleep", _explode):
            stats = tasks.run_bullboard_bridge.__wrapped__(max_iterations=1)

        # received == 0 took the grow-backoff branch; the early dict is exact.
        self.assertEqual(
            stats,
            {"received": 0, "broadcast": 0, "errors": 1, "skipped_not_leader": 0},
        )
