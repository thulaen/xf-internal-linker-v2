#!/usr/bin/env python3
"""Tests for the Django deploy-check hook scope."""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


HOOK_PATH = Path(__file__).with_name("check-django-deploy.py")


def _load_hook():
    spec = importlib.util.spec_from_file_location("check_django_deploy", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DjangoDeployHookScopeTests(unittest.TestCase):
    def test_test_settings_file_does_not_trigger_deploy_check(self) -> None:
        hook = _load_hook()
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="backend/config/settings/test.py\n",
            stderr="",
        )

        with patch.object(hook.subprocess, "run", return_value=completed):
            self.assertEqual(hook._staged_relevant(), [])

    def test_base_settings_file_still_triggers_deploy_check(self) -> None:
        hook = _load_hook()
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="System check identified no issues",
            stderr="",
        )

        with (
            patch.object(
                hook,
                "_staged_relevant",
                return_value=["backend/config/settings/base.py"],
            ),
            patch.object(hook.subprocess, "run", return_value=completed) as run,
        ):
            self.assertEqual(hook.main(), 0)

        run.assert_called_once()

    def test_deploy_check_uses_production_security_scope(self) -> None:
        hook = _load_hook()
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="System check identified no issues",
            stderr="",
        )

        with (
            patch.object(
                hook,
                "_staged_relevant",
                return_value=["backend/config/settings/base.py"],
            ),
            patch.object(hook.subprocess, "run", return_value=completed) as run,
        ):
            self.assertEqual(hook.main(), 0)

        cmd = run.call_args.args[0]
        self.assertIn("DJANGO_SETTINGS_MODULE=config.settings.production", cmd)
        self.assertIn("--tag", cmd)
        self.assertIn("security", cmd)


if __name__ == "__main__":
    unittest.main()
