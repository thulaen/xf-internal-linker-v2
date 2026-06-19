"""Unit tests for the Kubernetes self-heal helper."""

from __future__ import annotations

import json
import subprocess

from scripts import k8s_self_heal as heal


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _node(ready: bool) -> str:
    status = "True" if ready else "Unknown"
    return json.dumps({"status": {"conditions": [{"type": "Ready", "status": status}]}})


def _deployments(available: bool) -> str:
    count = 1 if available else 0
    return json.dumps(
        {
            "items": [
                {
                    "metadata": {"name": "backend"},
                    "spec": {"replicas": 1},
                    "status": {"availableReplicas": count},
                }
            ]
        }
    )


def _url_ok(url, timeout):
    return True, "HTTP 200"


def _url_down(url, timeout):
    return False, "connection refused"


def _policy(tmp_path):
    return heal.RecoveryPolicy(
        app_restart_cooldown_seconds=300,
        lock_stale_seconds=300,
        lock_path=tmp_path / "self-heal.lock",
        state_path=tmp_path / "self-heal-state.json",
    )


def test_inspect_cluster_reports_not_ready_and_unavailable_deployment():
    def runner(args, timeout):
        command = args[-1]
        if "get node" in command:
            return _completed(_node(False))
        return _completed(_deployments(False))

    state = heal.inspect_cluster(
        runner=runner,
        deployments=("backend",),
        url_checker=_url_down,
    )

    assert not state.healthy
    assert not state.dell_ready
    assert state.unavailable_deployments == ("backend",)
    assert not state.session_gate_ok


def test_inspect_cluster_requires_session_gate_url():
    def runner(args, timeout):
        return _completed(_node(True) if "get node" in args[-1] else _deployments(True))

    state = heal.inspect_cluster(runner=runner, url_checker=_url_down)

    assert not state.healthy
    assert state.dell_ready
    assert not state.unavailable_deployments
    assert "session gate failed" in state.detail


def test_heal_recovers_after_service_restart_without_reboot():
    calls = []
    checks = {"node": 0, "deploy": 0}

    def runner(args, timeout):
        calls.append(args)
        if args[:2] != ["ssh", "mint-wifi"]:
            return _completed("active\nactive\n")
        if "get node" in args[-1]:
            checks["node"] += 1
            return _completed(_node(checks["node"] > 1))
        checks["deploy"] += 1
        return _completed(_deployments(checks["deploy"] > 1))

    result = heal.heal_cluster(
        runner=runner,
        url_checker=_url_ok,
        sleep=lambda seconds: None,
    )

    assert result.ok
    assert "service restart" in result.message
    assert not any("sudo reboot" in " ".join(call) for call in calls)


def test_heal_does_not_restart_services_for_session_gate_only_failure():
    calls = []

    def runner(args, timeout):
        calls.append(args)
        if "get node" in args[-1]:
            return _completed(_node(True))
        return _completed(_deployments(True))

    result = heal.heal_cluster(
        runner=runner,
        url_checker=_url_down,
        sleep=lambda seconds: None,
    )

    assert not result.ok
    assert "Manual review" in result.message
    assert any("only the session gate failed" in action for action in result.actions)
    assert not any("sudo systemctl restart" in " ".join(call) for call in calls)
    assert not any("rollout restart" in " ".join(call) for call in calls)


def test_heal_recovers_after_app_deployment_restart(tmp_path):
    calls = []
    rolled_out = False

    def runner(args, timeout):
        nonlocal rolled_out
        calls.append(args)
        joined = " ".join(args)
        if "kubectl get --raw=/readyz" in joined:
            return _completed("ok")
        if "/proc/swaps" in joined:
            return _completed("0\n")
        if "sudo systemctl restart" in joined:
            return _completed("active\nactive\n")
        if "rollout restart" in joined:
            rolled_out = True
            return _completed("restarted")
        if "get node" in args[-1]:
            return _completed(_node(True))
        return _completed(_deployments(rolled_out))

    def url_checker(url, timeout):
        return (rolled_out, "HTTP 200" if rolled_out else "HTTP 502")

    result = heal.heal_cluster(
        runner=runner,
        url_checker=url_checker,
        sleep=lambda seconds: None,
        policy=_policy(tmp_path),
    )

    assert result.ok
    assert "app deployment restart" in result.message
    rollout_calls = [" ".join(call) for call in calls if "rollout restart" in " ".join(call)]
    assert rollout_calls
    assert "deployment/backend" in rollout_calls[0]
    assert "deployment/frontend" not in rollout_calls[0]
    assert not any("sudo reboot" in " ".join(call) for call in calls)


def test_heal_refuses_app_restart_when_mint_api_is_slow(tmp_path):
    calls = []
    clock_values = iter((0.0, 10.0, 10.0))

    def runner(args, timeout):
        calls.append(args)
        joined = " ".join(args)
        if "kubectl get --raw=/readyz" in joined:
            return _completed("ok")
        if "sudo systemctl restart" in joined:
            return _completed("active\nactive\n")
        if "get node" in args[-1]:
            return _completed(_node(True))
        return _completed(_deployments(False))

    result = heal.heal_cluster(
        runner=runner,
        url_checker=_url_down,
        sleep=lambda seconds: None,
        policy=_policy(tmp_path),
        clock=lambda: next(clock_values),
    )

    assert not result.ok
    assert any("Mint Kubernetes API was slow" in action for action in result.actions)
    assert not any("rollout restart" in " ".join(call) for call in calls)


def test_heal_refuses_app_restart_when_mint_uses_swap(tmp_path):
    calls = []

    def runner(args, timeout):
        calls.append(args)
        joined = " ".join(args)
        if "kubectl get --raw=/readyz" in joined:
            return _completed("ok")
        if "/proc/swaps" in joined:
            return _completed("2048\n")
        if "sudo systemctl restart" in joined:
            return _completed("active\nactive\n")
        if "get node" in args[-1]:
            return _completed(_node(True))
        return _completed(_deployments(False))

    result = heal.heal_cluster(
        runner=runner,
        url_checker=_url_down,
        sleep=lambda seconds: None,
        policy=_policy(tmp_path),
    )

    assert not result.ok
    assert any("Mint is using" in action for action in result.actions)
    assert not any("rollout restart" in " ".join(call) for call in calls)


def test_heal_refuses_app_restart_during_cooldown(tmp_path):
    calls = []
    policy = _policy(tmp_path)
    policy.state_path.write_text('{"last_app_restart_at": 100.0}', encoding="utf-8")

    def runner(args, timeout):
        calls.append(args)
        joined = " ".join(args)
        if "kubectl get --raw=/readyz" in joined:
            return _completed("ok")
        if "/proc/swaps" in joined:
            return _completed("0\n")
        if "sudo systemctl restart" in joined:
            return _completed("active\nactive\n")
        if "get node" in args[-1]:
            return _completed(_node(True))
        return _completed(_deployments(False))

    result = heal.heal_cluster(
        runner=runner,
        url_checker=_url_down,
        sleep=lambda seconds: None,
        policy=policy,
        clock=lambda: 120.0,
    )

    assert not result.ok
    assert any("cooldown" in action for action in result.actions)
    assert not any("rollout restart" in " ".join(call) for call in calls)


def test_heal_requires_reboot_flag_before_rebooting():
    def runner(args, timeout):
        if args[:1] == ["ssh"] and "sudo systemctl restart" in args[-1]:
            return _completed("restart failed", returncode=1)
        return _completed(_node(False) if "get node" in args[-1] else _deployments(False))

    result = heal.heal_cluster(
        runner=runner,
        url_checker=_url_down,
        sleep=lambda seconds: None,
    )

    assert not result.ok
    assert "--allow-reboot" in result.message


def test_heal_reports_service_restart_timeout_without_crashing():
    def runner(args, timeout):
        if args[:2] != ["ssh", "mint-wifi"]:
            raise subprocess.TimeoutExpired(args, timeout)
        return _completed(_node(False) if "get node" in args[-1] else _deployments(False))

    result = heal.heal_cluster(
        runner=runner,
        url_checker=_url_down,
        sleep=lambda seconds: None,
    )

    assert not result.ok
    assert any("timed out" in action for action in result.actions)


def test_heal_reboots_only_when_allowed():
    calls = []
    rebooted = False

    def runner(args, timeout):
        nonlocal rebooted
        calls.append(args)
        joined = " ".join(args)
        if "sudo systemctl restart" in joined:
            return _completed("restart failed", returncode=1)
        if "sudo reboot" in joined:
            rebooted = True
            return _completed("")
        if rebooted:
            return _completed(_node(True) if "get node" in args[-1] else _deployments(True))
        return _completed(_node(False) if "get node" in args[-1] else _deployments(False))

    result = heal.heal_cluster(
        allow_reboot=True,
        runner=runner,
        url_checker=_url_ok,
        sleep=lambda seconds: None,
    )

    assert result.ok
    assert any("sudo reboot" in " ".join(call) for call in calls)
