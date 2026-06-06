"""Convention-named coverage for apps/core/apps.py startup helpers.

Pins the behaviour of ``_consume_safe_mode_boot_flag`` — the "panic recovery"
path that, when a prior session armed ``system.boot_safe_once``, forces
``system.performance_mode`` to ``"safe"`` and clears the armed flag.

The audit-trail helper ``_record_safe_mode_history`` is patched out so these
tests do not pull in the ``suggestions`` app at boot time; the function already
swallows its failures, so patching it keeps the test focused on the AppSetting
state transition that matters.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.core import apps as core_apps
from apps.core.models import AppSetting


class ConsumeSafeModeBootFlagTests(TestCase):
    def _consume(self) -> None:
        # _record_safe_mode_history would lazy-import suggestions; patch it so
        # the test exercises only the AppSetting update_or_create + delete.
        with patch.object(core_apps, "_record_safe_mode_history") as recorder:
            core_apps._consume_safe_mode_boot_flag(sender=None)
        self._recorder = recorder

    def test_armed_flag_forces_safe_mode_and_clears_flag(self) -> None:
        AppSetting.objects.create(
            key="system.boot_safe_once", value="true", value_type="bool"
        )
        AppSetting.objects.create(
            key="system.performance_mode",
            value="high",
            value_type="str",
            category="performance",
        )

        self._consume()

        # Performance mode is forced to 'safe' via update_or_create.
        mode = AppSetting.objects.get(key="system.performance_mode")
        self.assertEqual(mode.value, "safe")
        self.assertEqual(mode.value_type, "str")
        self.assertEqual(mode.category, "performance")
        # The one-shot armed flag is deleted so it does not fire again.
        self.assertFalse(
            AppSetting.objects.filter(key="system.boot_safe_once").exists()
        )
        # The audit trail is recorded with the prior value it replaced.
        self._recorder.assert_called_once_with("high")

    def test_creates_safe_mode_when_none_existed(self) -> None:
        AppSetting.objects.create(
            key="system.boot_safe_once", value="true", value_type="bool"
        )

        self._consume()

        # update_or_create must CREATE the performance_mode row when absent.
        mode = AppSetting.objects.get(key="system.performance_mode")
        self.assertEqual(mode.value, "safe")
        # Prior value defaults to 'default' when no row existed.
        self._recorder.assert_called_once_with("default")

    def test_unarmed_flag_is_a_noop(self) -> None:
        AppSetting.objects.create(
            key="system.performance_mode",
            value="high",
            value_type="str",
            category="performance",
        )

        self._consume()

        # No armed flag -> early return, performance mode untouched.
        self.assertEqual(
            AppSetting.objects.get(key="system.performance_mode").value, "high"
        )
        self._recorder.assert_not_called()
