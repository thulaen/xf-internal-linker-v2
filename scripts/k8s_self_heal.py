#!/usr/bin/env python3
"""Recover the small Kubernetes cluster when the Dell worker stops reporting."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
import tempfile
from collections.abc import Callable, Sequence
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_MINT_HOST = "mint-wifi"
DEFAULT_DELL_NODE = "dell-ubuntu-01-optiplex-micro-7010"
DEFAULT_NAMESPACE = "xf-app"
DEFAULT_DEPLOYMENTS = ("backend", "frontend", "pgbouncer", "valkey")
DEFAULT_SESSION_GATE_URL = "http://192.168.0.91:30080/api/session-gate/"
COMMAND_TIMEOUT_SECONDS = 20
URL_TIMEOUT_SECONDS = 8
SSH_TIMEOUT_SECONDS = 45
POLL_ATTEMPTS = 2
POLL_DELAY_SECONDS = 10
MINT_API_SLOW_SECONDS = 5.0
APP_RESTART_COOLDOWN_SECONDS = 30 * 60
LOCK_STALE_SECONDS = 20 * 60
DEFAULT_RUNTIME_DIR = Path(tempfile.gettempdir()) / "xf-linker"
DEFAULT_LOCK_PATH = DEFAULT_RUNTIME_DIR / "k8s-self-heal.lock"
DEFAULT_STATE_PATH = DEFAULT_RUNTIME_DIR / "k8s-self-heal-state.json"

CommandRunner = Callable[[Sequence[str], int], subprocess.CompletedProcess[str]]
UrlChecker = Callable[[str, int], tuple[bool, str]]


@dataclass(frozen=True)
class ClusterState:
    dell_ready: bool
    unavailable_deployments: tuple[str, ...]
    session_gate_ok: bool
    detail: str

    @property
    def healthy(self) -> bool:
        return self.dell_ready and not self.unavailable_deployments and self.session_gate_ok


@dataclass(frozen=True)
class HealResult:
    ok: bool
    actions: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class RecoveryPolicy:
    app_restart_cooldown_seconds: int = APP_RESTART_COOLDOWN_SECONDS
    lock_stale_seconds: int = LOCK_STALE_SECONDS
    mint_api_slow_seconds: float = MINT_API_SLOW_SECONDS
    lock_path: Path = DEFAULT_LOCK_PATH
    state_path: Path = DEFAULT_STATE_PATH


@dataclass(frozen=True)
class SafetyCheck:
    ok: bool
    detail: str


def run_command(args: Sequence[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run a command with bounded waiting and captured text."""
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def inspect_cluster(
    *,
    mint_host: str = DEFAULT_MINT_HOST,
    namespace: str = DEFAULT_NAMESPACE,
    dell_node: str = DEFAULT_DELL_NODE,
    deployments: Sequence[str] = DEFAULT_DEPLOYMENTS,
    session_gate_url: str = DEFAULT_SESSION_GATE_URL,
    runner: CommandRunner = run_command,
    url_checker: UrlChecker = None,
) -> ClusterState:
    """Return node and deployment health from Mint-side Kubernetes commands."""
    checker = url_checker or check_url
    node_json = _kubectl_json(
        mint_host,
        ("get", "node", dell_node, "-o", "json"),
        runner,
    )
    deploy_json = _kubectl_json(
        mint_host,
        ("-n", namespace, "get", "deploy", *deployments, "-o", "json"),
        runner,
    )
    dell_ready = _node_ready(node_json)
    unavailable = tuple(_unavailable_deployments(deploy_json))
    session_gate_ok, session_detail = checker(session_gate_url, URL_TIMEOUT_SECONDS)
    detail = _state_detail(dell_ready, unavailable, session_gate_ok, session_detail)
    return ClusterState(dell_ready, unavailable, session_gate_ok, detail)


def heal_cluster(
    *,
    allow_reboot: bool = False,
    runner: CommandRunner = run_command,
    url_checker: UrlChecker = None,
    sleep: Callable[[float], None] = time.sleep,
    policy: RecoveryPolicy | None = None,
    clock: Callable[[], float] = time.time,
) -> HealResult:
    """Try safe Dell service recovery, then report whether reboot is needed."""
    checker = url_checker or check_url
    policy = policy or RecoveryPolicy()
    before = inspect_cluster(runner=runner, url_checker=checker)
    actions: list[str] = [f"initial: {before.detail}"]
    quick_result = _quick_heal_result(before, actions)
    if quick_result is not None:
        return quick_result

    after_services = _restart_services_and_poll(actions, runner, checker, sleep)
    if after_services.healthy:
        return HealResult(True, tuple(actions), "Cluster recovered after service restart.")

    after_apps, app_result = _try_app_restart_recovery(
        after_services,
        actions,
        runner,
        checker,
        sleep,
        policy,
        clock,
    )
    if app_result is not None:
        return app_result

    return _try_reboot_recovery(after_apps, actions, allow_reboot, runner, checker, sleep)


def _quick_heal_result(state: ClusterState, actions: list[str]) -> HealResult | None:
    if state.healthy:
        return HealResult(True, tuple(actions), "Cluster is already healthy.")
    if not _session_gate_only_failure(state):
        return None
    actions.append("restart skipped: Dell and deployments are healthy; only the session gate failed")
    return HealResult(
        False,
        tuple(actions),
        "Session gate is unhealthy, but Dell and app deployments look healthy. Manual review is needed.",
    )


def _restart_services_and_poll(
    actions: list[str],
    runner: CommandRunner,
    checker: UrlChecker,
    sleep: Callable[[float], None],
) -> ClusterState:
    actions.append(_restart_dell_services(runner))
    state = _poll_until_healthy(runner=runner, url_checker=checker, sleep=sleep)
    actions.append(f"after service restart: {state.detail}")
    return state


def _try_app_restart_recovery(
    state: ClusterState,
    actions: list[str],
    runner: CommandRunner,
    checker: UrlChecker,
    sleep: Callable[[float], None],
    policy: RecoveryPolicy,
    clock: Callable[[], float],
) -> tuple[ClusterState, HealResult | None]:
    app_actions = _try_app_deployment_restart(state, runner, policy, clock)
    actions.extend(app_actions)
    if not _app_restart_requested(app_actions):
        return state, None
    after_rollout = _poll_until_healthy(runner=runner, url_checker=checker, sleep=sleep)
    actions.append(f"after app restart: {after_rollout.detail}")
    if after_rollout.healthy:
        return after_rollout, HealResult(
            True,
            tuple(actions),
            "Cluster recovered after app deployment restart.",
        )
    return after_rollout, None


def _app_restart_requested(actions: Sequence[str]) -> bool:
    return bool(actions) and actions[-1].startswith("restarted ")


def _try_reboot_recovery(
    state: ClusterState,
    actions: list[str],
    allow_reboot: bool,
    runner: CommandRunner,
    checker: UrlChecker,
    sleep: Callable[[float], None],
) -> HealResult:
    if state.dell_ready:
        return HealResult(
            False,
            tuple(actions),
            "Cluster is unhealthy, but app restart was refused or did not recover it. Manual review is needed.",
        )
    if not allow_reboot:
        return HealResult(
            False,
            tuple(actions),
            "Dell still needs a reboot. Re-run with --allow-reboot only if app downtime is approved.",
        )
    actions.append(_reboot_dell(runner))
    after_reboot = _poll_until_healthy(runner=runner, url_checker=checker, sleep=sleep)
    actions.append(f"after reboot: {after_reboot.detail}")
    if after_reboot.healthy:
        return HealResult(True, tuple(actions), "Cluster recovered after Dell reboot.")
    return HealResult(False, tuple(actions), "Dell reboot finished, but Kubernetes is still unhealthy.")


def _try_app_deployment_restart(
    state: ClusterState,
    runner: CommandRunner,
    policy: RecoveryPolicy,
    clock: Callable[[], float],
) -> tuple[str, ...]:
    targets = state.unavailable_deployments
    if not targets:
        return ("app deployment restart skipped: no unavailable deployment was identified",)
    safety = _app_restart_safety(state, runner, policy, clock)
    if not safety.ok:
        return (f"app deployment restart skipped: {safety.detail}",)
    locked, lock_detail = _acquire_app_restart_lock(policy, clock)
    if not locked:
        return (f"app deployment restart skipped: {lock_detail}",)
    try:
        message = _restart_app_deployments(runner, targets)
        _record_app_restart(policy, clock, targets)
        return (message,)
    finally:
        _release_app_restart_lock(policy)


def _session_gate_only_failure(state: ClusterState) -> bool:
    return state.dell_ready and not state.unavailable_deployments and not state.session_gate_ok


def _app_restart_safety(
    state: ClusterState,
    runner: CommandRunner,
    policy: RecoveryPolicy,
    clock: Callable[[], float],
) -> SafetyCheck:
    if not state.dell_ready:
        return SafetyCheck(False, "Dell is NotReady")
    checks = (
        _mint_api_fast(runner, policy, clock),
        _mint_swap_clear(runner),
        _cooldown_clear(policy, clock),
        _lock_clear(policy, clock),
    )
    for check in checks:
        if not check.ok:
            return check
    return SafetyCheck(True, "safe to restart unavailable app deployments")


def _kubectl_json(
    mint_host: str,
    kubectl_args: Sequence[str],
    runner: CommandRunner,
) -> dict:
    command = ["kubectl", *kubectl_args, "--request-timeout=10s"]
    result = runner(["ssh", mint_host, shlex.join(command)], COMMAND_TIMEOUT_SECONDS)
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Kubernetes command failed: {output}")
    return json.loads(result.stdout)


def _node_ready(node_json: dict) -> bool:
    for condition in node_json.get("status", {}).get("conditions", []):
        if condition.get("type") == "Ready":
            return condition.get("status") == "True"
    return False


def _unavailable_deployments(deploy_json: dict) -> list[str]:
    unavailable = []
    for item in deploy_json.get("items", []):
        desired = item.get("spec", {}).get("replicas", 1)
        available = item.get("status", {}).get("availableReplicas", 0)
        if available < desired:
            unavailable.append(item.get("metadata", {}).get("name", "<unknown>"))
    return unavailable


def check_url(url: str, timeout: int) -> tuple[bool, str]:
    """Return whether the user-facing session gate answers."""
    try:
        with urlopen(url, timeout=timeout) as response:
            status = getattr(response, "status", 0)
    except (OSError, URLError) as exc:
        return False, str(exc)
    if 200 <= status < 300:
        return True, f"HTTP {status}"
    return False, f"HTTP {status}"


def _state_detail(
    dell_ready: bool,
    unavailable: Sequence[str],
    session_gate_ok: bool,
    session_detail: str,
) -> str:
    node = "Dell Ready" if dell_ready else "Dell NotReady"
    session_gate = "session gate OK" if session_gate_ok else f"session gate failed: {session_detail}"
    if not unavailable:
        return f"{node}; deployments available; {session_gate}"
    return f"{node}; unavailable deployments: {', '.join(unavailable)}; {session_gate}"


def _restart_dell_services(runner: CommandRunner) -> str:
    command = (
        "sudo systemctl restart ssh k3s-agent && "
        "systemctl is-active ssh && systemctl is-active k3s-agent"
    )
    try:
        result = runner(_dell_ssh(command), SSH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return "Dell service restart timed out"
    if result.returncode == 0:
        return "restarted Dell SSH and Kubernetes agent"
    output = (result.stderr or result.stdout).strip()
    return f"Dell service restart failed: {output}"


def _restart_app_deployments(runner: CommandRunner, deployments: Sequence[str]) -> str:
    targets = [f"deployment/{name}" for name in deployments]
    command = [
        "kubectl",
        "-n",
        DEFAULT_NAMESPACE,
        "rollout",
        "restart",
        *targets,
        "--request-timeout=10s",
    ]
    try:
        result = runner(["ssh", DEFAULT_MINT_HOST, shlex.join(command)], COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return "app deployment restart timed out"
    if result.returncode == 0:
        return f"restarted {_join_names(deployments)} deployments"
    output = (result.stderr or result.stdout).strip()
    return f"app deployment restart failed: {output}"


def _mint_api_fast(
    runner: CommandRunner,
    policy: RecoveryPolicy,
    clock: Callable[[], float],
) -> SafetyCheck:
    started = clock()
    try:
        result = runner(
            ["ssh", DEFAULT_MINT_HOST, "kubectl get --raw=/readyz --request-timeout=5s"],
            COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return SafetyCheck(False, "Mint Kubernetes API timed out")
    elapsed = clock() - started
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        return SafetyCheck(False, f"Mint Kubernetes API failed: {output}")
    if elapsed > policy.mint_api_slow_seconds:
        return SafetyCheck(False, f"Mint Kubernetes API was slow ({elapsed:.1f}s)")
    return SafetyCheck(True, f"Mint Kubernetes API was healthy ({elapsed:.1f}s)")


def _mint_swap_clear(runner: CommandRunner) -> SafetyCheck:
    try:
        result = runner(
            ["ssh", DEFAULT_MINT_HOST, "awk 'NR>1 {used+=$3} END {print used+0}' /proc/swaps"],
            COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return SafetyCheck(False, "Mint swap check timed out")
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        return SafetyCheck(False, f"Mint swap check failed: {output}")
    used_kib = _parse_swap_kib(result.stdout)
    if used_kib > 0:
        return SafetyCheck(False, f"Mint is using {_format_mib(used_kib)} MiB of swap")
    return SafetyCheck(True, "Mint is not using swap")


def _cooldown_clear(policy: RecoveryPolicy, clock: Callable[[], float]) -> SafetyCheck:
    if not policy.state_path.exists():
        return SafetyCheck(True, "app restart cooldown is clear")
    try:
        data = json.loads(policy.state_path.read_text(encoding="utf-8"))
        last_restart = float(data.get("last_app_restart_at", 0))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return SafetyCheck(False, "app restart cooldown state could not be read")
    remaining = policy.app_restart_cooldown_seconds - (clock() - last_restart)
    if remaining > 0:
        return SafetyCheck(False, f"app restart cooldown has {remaining:.0f}s remaining")
    return SafetyCheck(True, "app restart cooldown is clear")


def _lock_clear(policy: RecoveryPolicy, clock: Callable[[], float]) -> SafetyCheck:
    if not policy.lock_path.exists():
        return SafetyCheck(True, "app restart lock is clear")
    age = clock() - policy.lock_path.stat().st_mtime
    if age < policy.lock_stale_seconds:
        return SafetyCheck(False, "another app restart is already running")
    return SafetyCheck(True, "stale app restart lock can be replaced")


def _acquire_app_restart_lock(policy: RecoveryPolicy, clock: Callable[[], float]) -> tuple[bool, str]:
    clear = _lock_clear(policy, clock)
    if not clear.ok:
        return False, clear.detail
    policy.lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"started_at": clock()}
    policy.lock_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return True, "app restart lock acquired"


def _release_app_restart_lock(policy: RecoveryPolicy) -> None:
    try:
        policy.lock_path.unlink()
    except FileNotFoundError:
        return


def _record_app_restart(
    policy: RecoveryPolicy,
    clock: Callable[[], float],
    deployments: Sequence[str],
) -> None:
    policy.state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_app_restart_at": clock(), "deployments": list(deployments)}
    policy.state_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _parse_swap_kib(output: str) -> int:
    try:
        return int(output.strip() or "0")
    except ValueError:
        return 0


def _format_mib(kib: int) -> str:
    return f"{kib / 1024:.0f}"


def _join_names(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _reboot_dell(runner: CommandRunner) -> str:
    try:
        result = runner(_dell_ssh("sudo reboot"), SSH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return "Dell reboot request timed out"
    if result.returncode in {0, 255}:
        return "requested Dell reboot"
    output = (result.stderr or result.stdout).strip()
    return f"Dell reboot request failed: {output}"


def _dell_ssh(command: str) -> list[str]:
    return [
        "ssh",
        "-tt",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=30",
        "-o",
        "ConnectionAttempts=1",
        "dell",
        command,
    ]


def _poll_until_healthy(
    *,
    runner: CommandRunner,
    url_checker: UrlChecker,
    sleep: Callable[[float], None],
) -> ClusterState:
    state = inspect_cluster(runner=runner, url_checker=url_checker)
    for _attempt in range(POLL_ATTEMPTS):
        if state.healthy:
            return state
        sleep(POLL_DELAY_SECONDS)
        state = inspect_cluster(runner=runner, url_checker=url_checker)
    return state


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Self-heal the Mint and Dell Kubernetes app.")
    parser.add_argument("--allow-reboot", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = heal_cluster(allow_reboot=args.allow_reboot)
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: Kubernetes self-heal could not inspect the cluster. {exc}", file=sys.stderr)
        return 2
    for action in result.actions:
        print(action)
    print(("OK: " if result.ok else "FAIL: ") + result.message)
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
