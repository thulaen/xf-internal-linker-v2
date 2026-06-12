"""Unit tests for scripts/run_lint_on_context.py (no Docker required).

These cover the pure, machine-independent logic: the tool-command registry, the
remote/local docker command construction, the routing-config read, and the
split-and-merge verdict (rc = worst slice, output traceable per machine). The
two slice runners are monkeypatched so no container ever starts under test.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    import importlib.util

    path = ROOT / "scripts" / "run_lint_on_context.py"
    spec = importlib.util.spec_from_file_location("run_lint_on_context", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_inner_command_per_tool():
    """Given each tool, When building the inner command, Then it matches the local form."""
    m = _mod()
    assert m._inner_command("ruff", ["apps/a.py"]) == ["ruff", "check", "apps/a.py"]
    assert m._inner_command("pylint", ["apps/a.py"]) == [
        "pylint", "--errors-only", "--disable=no-member", "apps/a.py"]
    assert m._inner_command("mypy", ["apps/a.py"]) == [
        "python", "-m", "mypy", "--config-file", "/repo/backend/mypy.ini", "apps/a.py"]
    assert m._inner_command("bandit", ["apps/a.py"]) == ["bandit", "-q", "apps/a.py"]


def test_inner_command_rejects_unknown_tool():
    """Given an unknown tool, When building a command, Then it raises ValueError."""
    m = _mod()
    with pytest.raises(ValueError):
        m._inner_command("flake8", ["apps/a.py"])


def test_remote_lint_cmd_uses_dell_context_volume_and_image():
    """Given a Dell slice, When building the remote command, Then it targets the dell context."""
    m = _mod()
    cmd = m._remote_lint_cmd("dell", "ruff", ["apps/a.py"])
    assert cmd[:5] == ["docker", "--context", "dell", "run", "--rm"]
    assert "xf_lint_repo:/repo" in cmd
    assert "DJANGO_SETTINGS_MODULE=config.settings.test" in cmd
    assert "DJANGO_SECRET_KEY=ci-fake-secret-key" in cmd
    assert "POSTGRES_PASSWORD=ci-fake-postgres-password" in cmd
    assert "xf-linker-backend-quality:latest" in cmd
    assert cmd[-3:] == ["ruff", "check", "apps/a.py"]
    # cwd is the synced source on the remote, never the local /app bind mount.
    assert "/repo/backend" in cmd


def test_lint_routing_config_puts_100_percent_on_dell():
    """Given the routing config, When read, Then Dell carries 100% of lint and Windows 0% (fail-closed)."""
    m = _mod()
    machines = {entry["name"]: entry for entry in m._load_lint_routing_config()["machines"]}
    assert machines["dell"]["weight"] == 1.0
    assert machines["dell"]["context"] == "dell"
    # The block really exists in the committed config.
    cfg = json.loads((ROOT / "config" / "mutation-routing.json").read_text(encoding="utf-8"))
    assert cfg["lint_machines"][0]["name"] == "dell"
    assert cfg["lint_machines"][0]["weight"] == 1.0


def test_run_tool_sharded_no_files_is_clean():
    """Given no changed files, When linting, Then the verdict is a clean no-op."""
    m = _mod()
    rc, out = m.run_tool_sharded("ruff", [])
    assert rc == 0
    assert "no changed files" in out


def _fake_routing():
    """A stand-in for machine_routing with two machines and real split/dispatch."""
    class _R:
        @staticmethod
        def _select_machines(_cfg):
            return [
                {"name": "dell", "transport": "docker_context", "context": "dell", "share": 1.0},
            ]

        @staticmethod
        def _partition_weighted(items, machines):
            return {"dell": items}

        @staticmethod
        def _dispatch_to_machines(machines, plan, per_machine):
            for machine in machines:
                slice_items = plan.get(machine["name"]) or []
                if slice_items:
                    per_machine(machine, slice_items)

    return _R()


def test_run_tool_sharded_merges_worst_rc_and_labels_machines(monkeypatch):
    """Given a Dell-clean / Windows-failing split, When merged, Then rc is the worst (fail)."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_lint_slice_on_remote", lambda ctx, tool, files: (2, "E001 bad thing\n"))

    rc, out = m.run_tool_sharded("ruff", ["apps/a.py", "apps/b.py"])

    assert rc == 2  # slice failed -> overall fail
    assert "dell" in out
    assert "E001 bad thing" in out


def test_run_tool_sharded_fails_closed_when_remote_untrusted(monkeypatch):
    """Given Dell returns untrusted (None), When linting, Then it fails closed."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_lint_slice_on_remote", lambda ctx, tool, files: None)

    rc, out = m.run_tool_sharded("ruff", ["apps/a.py", "apps/b.py"])

    assert rc == 1
    assert "Dell source sync or manifest verification failed for ruff" in out


def test_run_tool_sharded_fails_closed_for_non_docker_context(monkeypatch):
    """Given a non-docker_context machine, When linting, Then it fails closed."""
    m = _mod()
    
    class _R_Windows:
        @staticmethod
        def _select_machines(_cfg):
            return [{"name": "windows", "transport": "docker_local", "share": 1.0}]
        @staticmethod
        def _partition_weighted(items, machines):
            return {"windows": items}
        @staticmethod
        def _dispatch_to_machines(machines, plan, per_machine):
            for machine in machines:
                per_machine(machine, plan.get(machine["name"]) or [])

    monkeypatch.setattr(m, "_load_machine_routing", lambda: _R_Windows())
    monkeypatch.setattr(m, "_lint_slice_on_remote", lambda ctx, tool, files: (0, ""))

    rc, out = m.run_tool_sharded("ruff", ["apps/a.py", "apps/b.py"])

    assert rc == 1
    assert "transport not allowed" in out


def test_run_lint_writes_one_evidence_row_per_tool(monkeypatch, tmp_path):
    """Given evidence_out, When linting, Then one QualityEvidence row is written per tool."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_lint_slice_on_remote", lambda ctx, tool, files: (0, ""))
    ev = tmp_path / "python.jsonl"

    rc = m.run_lint(["ruff", "pylint"], ["apps/a.py", "apps/b.py"], evidence_out=ev)

    assert rc == 0
    rows = [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {r["tool_name"] for r in rows} == {"ruff", "pylint"}
    assert all(r["status"] == "passed" for r in rows)
    assert all(r["check_type"] == "static_analysis" for r in rows)


def test_run_lint_bandit_failure_is_a_failed_security_evidence_row(monkeypatch, tmp_path):
    """Given bandit fails, When evidence_out is set, Then a failed security row is recorded."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_lint_slice_on_remote", lambda ctx, tool, files: (1, "B101\n"))
    ev = tmp_path / "python.jsonl"

    rc = m.run_lint(["bandit"], ["apps/a.py"], bandit_files=["apps/a.py"], evidence_out=ev)

    assert rc == 1
    rows = [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["tool_name"] == "bandit"
    assert rows[0]["check_type"] == "security"
    assert rows[0]["status"] == "failed"


def test_run_lint_empty_bandit_files_records_no_targets_pass(monkeypatch, tmp_path):
    """Given no app files for bandit, When evidence_out is set, Then a clean no-targets row is written."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_lint_slice_on_remote", lambda ctx, tool, files: (0, ""))
    ev = tmp_path / "python.jsonl"

    rc = m.run_lint(["bandit"], ["apps/a.py"], bandit_files=[], evidence_out=ev)

    assert rc == 0
    rows = [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["failure_fingerprint"] == "bandit:no-changed-targets"
    assert rows[0]["status"] == "passed"


def test_dependency_audit_runs_tools_and_records_evidence(monkeypatch, tmp_path):
    """Given --dependency-audit, When run, Then it executes pip-audit and safety check on Dell and logs evidence."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_sync_source_to_context", lambda ctx, env: None)
    
    ran_cmds = []
    def fake_run(cmd, env, timeout):
        ran_cmds.append(cmd)
        return 0, "All good!"
    
    monkeypatch.setattr(m, "_run", fake_run)
    ev = tmp_path / "python.jsonl"

    m.run_lint([], [], evidence_out=ev)
    m._run_dependency_audit(ev)

    assert any("pip-audit" in cmd for cmd in ran_cmds)
    assert any("safety" in cmd for cmd in ran_cmds)
    
    rows = [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {r["tool_name"] for r in rows} == {"pip-audit", "safety"}
    assert all(r["status"] == "passed" for r in rows)
    assert all(r["check_type"] == "security" for r in rows)
