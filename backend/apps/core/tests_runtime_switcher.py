"""Convention-named SimpleTestCase coverage for apps/core/runtime_switcher.py.

The drain-and-resume switcher flips ``system.master_pause`` so no new batches
start, waits up to ``MAX_DRAIN_SECONDS`` for in-flight leases to drain, then
writes the new runtime mode. The wait loop calls ``time.sleep`` and a real DB
count, so every test here either takes an early-return branch or patches
``_wait_for_drain`` so NO real sleep, network, or database call runs and the
mutation gate never hangs.

The literal tests pin the configured numbers with ``assertEqual`` (not ``>=``)
and the rejection message with an exact string compare so the diff-scoped
mutation gate's +1 / string-wrap mutants are killed rather than left alive.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core import runtime_switcher


class DrainConstantLiteralTests(SimpleTestCase):
    # assertEqual (not assertGreaterEqual): the mutation gate mutates
    # `MAX_DRAIN_SECONDS = 90` -> 91 and `POLL_INTERVAL_SECONDS = 2` -> 3; a
    # `>=` assertion would still pass on the mutant and leave it alive, blocking
    # the gate. Pinning the exact configured value kills both.
    def test_max_drain_seconds_is_90(self) -> None:
        self.assertEqual(runtime_switcher.MAX_DRAIN_SECONDS, 90)

    def test_poll_interval_seconds_is_2(self) -> None:
        self.assertEqual(runtime_switcher.POLL_INTERVAL_SECONDS, 2)

    def test_setting_keys_are_exact(self) -> None:
        # Exact-string equality kills the mutmut "XX...XX" string-wrap mutant
        # that a substring check would let survive.
        self.assertEqual(
            runtime_switcher.KEY_RUNTIME_MODE, "system.runtime_mode"
        )
        self.assertEqual(
            runtime_switcher.KEY_MASTER_PAUSE, "system.master_pause"
        )
        self.assertEqual(
            runtime_switcher.KEY_SWITCH_PENDING, "system.runtime_switch_pending"
        )


class SwitchRuntimeTargetGuardTests(SimpleTestCase):
    """Only ``target == "cpu"`` is accepted; everything else is rejected."""

    def test_non_cpu_target_is_rejected_with_exact_message(self) -> None:
        # AppSetting is imported lazily inside switch_runtime; the guard returns
        # before any model access, so no patch is needed and no DB is touched.
        result = runtime_switcher.switch_runtime(target="gpu")
        # Exact dict match kills both the boolean flip (ok=False -> True) and
        # the string-wrap mutant on the error message.
        self.assertEqual(result, {"ok": False, "error": "target must be 'cpu'"})

    def test_empty_target_is_rejected(self) -> None:
        result = runtime_switcher.switch_runtime(target="")
        self.assertFalse(result["ok"])


class SwitchRuntimeFastPathTests(SimpleTestCase):
    """When already on the target, the switch is a skipped no-op."""

    def _app_setting(self, *, current_mode: str) -> MagicMock:
        app_setting = MagicMock()
        # _read -> AppSetting.objects.filter(...).values_list(...).first()
        chain = app_setting.objects.filter.return_value.values_list.return_value
        chain.first.return_value = current_mode
        return app_setting

    def test_already_on_cpu_returns_skipped_without_draining(self) -> None:
        app_setting = self._app_setting(current_mode="cpu")
        drain = MagicMock()
        with patch("apps.core.models.AppSetting", app_setting), patch.object(
            runtime_switcher, "_wait_for_drain", drain
        ):
            result = runtime_switcher.switch_runtime(target="cpu")
        # Fast path must not enter the drain loop at all.
        drain.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["target"], "cpu")
        self.assertEqual(result["drain_waited_s"], 0)


class SwitchRuntimeCommitTests(SimpleTestCase):
    """A real switch writes the mode and clears the pause + pending flags."""

    def test_commit_clears_pause_and_returns_drain_seconds(self) -> None:
        app_setting = MagicMock()
        # Current mode reads back as "gpu" so target "cpu" is a real switch.
        chain = app_setting.objects.filter.return_value.values_list.return_value
        chain.first.return_value = "gpu"
        with patch("apps.core.models.AppSetting", app_setting), patch.object(
            runtime_switcher, "_wait_for_drain", return_value=7
        ):
            result = runtime_switcher.switch_runtime(target="cpu")
        self.assertTrue(result["ok"])
        self.assertFalse(result.get("skipped", False))
        self.assertEqual(result["target"], "cpu")
        self.assertEqual(result["previous"], "gpu")
        # Exact value (not >=) kills the +1 mutant on the drain-seconds return.
        self.assertEqual(result["drain_waited_s"], 7)
        self.assertTrue(result["warmed"])

    def test_drain_skipped_when_wait_for_drain_is_false(self) -> None:
        app_setting = MagicMock()
        chain = app_setting.objects.filter.return_value.values_list.return_value
        chain.first.return_value = "gpu"
        drain = MagicMock()
        with patch("apps.core.models.AppSetting", app_setting), patch.object(
            runtime_switcher, "_wait_for_drain", drain
        ):
            result = runtime_switcher.switch_runtime(
                target="cpu", wait_for_drain=False
            )
        drain.assert_not_called()
        self.assertEqual(result["drain_waited_s"], 0)


class RunWarmupTests(SimpleTestCase):
    """CPU runtime has no warmup step and always reports warmed."""

    def test_run_warmup_always_true(self) -> None:
        self.assertTrue(runtime_switcher._run_warmup("cpu", None))
        self.assertTrue(runtime_switcher._run_warmup("cpu", MagicMock()))
