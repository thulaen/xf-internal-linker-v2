#!/usr/bin/env python3
"""Tests for the Dell-only execution lock on the local Windows machine (MSI).

The guard (scripts/_dell_only_guard.sh) must make every quality/mutation
runner refuse to execute tests, lint, coverage, or mutation work on the
bare Windows host — even when docker-context or split environment
variables are overridden — while CI runners and containers stay exempt.
"""

from __future__ import annotations

import os
import platform
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = "scripts/_dell_only_guard.sh"

# Hooks run under Git Bash (MINGW). A bare "bash" from Python resolves to
# WSL bash on this machine, which reports Linux — so call Git Bash directly.
_GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
_BASH = str(_GIT_BASH) if _GIT_BASH.exists() else "bash"

# The behavior tests exercise the Git Bash hook shell of the Windows host
# itself; on Dell/CI (Linux, containers) only the wiring tests apply.
_ON_WINDOWS = platform.system() == "Windows"


def _bash(snippet: str, **env_overrides: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CI", "GITHUB_ACTIONS")}
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        [_BASH, "-c", f"source {GUARD}; {snippet}"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )


@unittest.skipUnless(_ON_WINDOWS, "exercises the Windows host's Git Bash")
class MsiHostDetectionTests(unittest.TestCase):
    def test_bare_windows_host_is_detected(self) -> None:
        # This test suite itself runs on the MSI's Git Bash, so detection
        # must fire here with CI variables stripped.
        result = _bash("xf_on_msi_host")
        self.assertEqual(result.returncode, 0)

    def test_ci_runners_are_exempt(self) -> None:
        for ci_var in ("CI", "GITHUB_ACTIONS"):
            result = _bash("xf_on_msi_host", **{ci_var: "true"})
            self.assertEqual(result.returncode, 1, f"{ci_var}=true must exempt")


@unittest.skipUnless(_ON_WINDOWS, "exercises the Windows host's Git Bash")
class RemoteContextLockTests(unittest.TestCase):
    def test_local_docker_contexts_are_blocked_on_msi(self) -> None:
        for context in ("default", "desktop-linux", "__local__", "local", ""):
            result = _bash(
                f'xf_require_remote_context demo-runner "{context}"'
            )
            self.assertEqual(result.returncode, 1, f"context={context!r}")
            self.assertIn("blocked on this Windows machine", result.stderr)
            self.assertIn("UNBLOCK", result.stderr)

    def test_dell_context_is_allowed(self) -> None:
        result = _bash('xf_require_remote_context demo-runner "dell"')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_ci_runner_may_use_any_context(self) -> None:
        result = _bash(
            'xf_require_remote_context demo-runner "default"', CI="true"
        )
        self.assertEqual(result.returncode, 0)

    def test_ssh_home_is_recovered_from_windows_profile(self) -> None:
        result = _bash(
            'xf_prepare_ssh_home; test -n "$HOME"',
            HOME=None,
            USERPROFILE=r"C:\Users\goldm",
        )
        self.assertEqual(result.returncode, 0)


@unittest.skipUnless(_ON_WINDOWS, "exercises the Windows host's Git Bash")
class LocalContainerLockTests(unittest.TestCase):
    def test_local_quality_container_is_blocked_on_msi(self) -> None:
        result = _bash("xf_block_local_quality_container demo-runner")
        self.assertEqual(result.returncode, 1)
        self.assertIn("blocked on this Windows machine", result.stderr)
        self.assertIn("Dell", result.stderr)

    def test_ci_runner_keeps_its_container_path(self) -> None:
        result = _bash(
            "xf_block_local_quality_container demo-runner", GITHUB_ACTIONS="true"
        )
        self.assertEqual(result.returncode, 0)


class GuardWiringTests(unittest.TestCase):
    """Every runner that could execute work locally must consult the guard."""

    def _text(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_context_runners_validate_their_context_override(self) -> None:
        expectations = {
            "scripts/run-python-mutation.sh": "$PYTHON_MUTATION_DOCKER_CONTEXT",
            "tools/quality/internal/run-rust-quality.sh": "$RUST_MUTATION_DOCKER_CONTEXT",
            "scripts/run-rust-mutation.sh": "$RUST_MUTATION_DOCKER_CONTEXT",
            "tools/quality/internal/run-angular-quality.sh": "$ANGULAR_DOCKER_CONTEXT",
            "scripts/run-angular-mutation.sh": "$ANGULAR_DOCKER_CONTEXT",
        }
        for rel, var in expectations.items():
            text = self._text(rel)
            self.assertIn("_dell_only_guard.sh", text, f"{rel} must source the guard")
            self.assertIn(f'xf_require_remote_context', text, rel)
            self.assertIn(var, text, rel)

    def test_python_quality_forces_dell_splits_and_guards_container(self) -> None:
        text = self._text("tools/quality/internal/run-python-quality.sh")
        self.assertIn("_dell_only_guard.sh", text)
        self.assertIn("xf_on_msi_host", text)
        self.assertIn("xf_block_local_quality_container", text)
        # The forced-split block must come before the env-default block reads.
        self.assertLess(
            text.find("xf_on_msi_host"),
            text.find('docker compose run --rm -T --name "$QUALITY_CONTAINER"'),
        )

    def test_machine_routing_rejects_local_contexts_on_windows(self) -> None:
        text = self._text("scripts/machine_routing.py")
        self.assertIn("_on_windows_host", text)
        self.assertIn("desktop-linux", text)


if __name__ == "__main__":
    unittest.main()
