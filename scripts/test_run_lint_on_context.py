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
    mod.dell_ssh_preflight.ssh_base_command = lambda context: ["ssh", context]
    return mod


def test_inner_command_per_tool():
    """Given each tool, When building the inner command, Then it matches the expected form."""
    m = _mod()
    assert m._inner_command("ruff", ["apps/a.py"]) == ["ruff", "check", "apps/a.py"]
    assert m._inner_command("mypy", ["apps/a.py"]) == [
        "dmypy", "run", "--timeout", "7200", "--",
        "--config-file", "/repo/backend/mypy.ini", "apps/a.py"]
    assert m._inner_command("bandit", ["apps/a.py"]) == ["bandit", "-q", "apps/a.py"]


def test_pylint_is_fully_retired():
    """Given the lint router and quality wrapper, When read, Then pylint is gone (ruff's PLE rules replaced it)."""
    router = (ROOT / "scripts" / "run_lint_on_context.py").read_text(encoding="utf-8")
    wrapper = (
        ROOT / "tools" / "quality" / "internal" / "run-python-quality.sh"
    ).read_text(encoding="utf-8")
    assert "pylint" not in router.lower()
    assert "pylint" not in wrapper.lower()


def test_ruff_config_selects_pylint_error_parity_rules():
    """Given backend/pyproject.toml, When parsed, Then ruff extends its selection with PLE (pylint-error parity)."""
    import tomllib

    cfg = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    assert "PLE" in cfg["tool"]["ruff"]["lint"]["extend-select"]


def test_pylint_not_installed_in_quality_images():
    """Given the quality Docker images, When read, Then neither installs pylint.

    pylint was retired in favour of ruff's PLE rules, so leaving the pip
    install line behind only bloats the image and confuses future agents.
    """
    backend_dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "pylint==" not in backend_dockerfile
    mutation_dockerfile = (ROOT / "tools" / "mutation" / "Dockerfile").read_text(encoding="utf-8")
    assert "pylint==" not in mutation_dockerfile


def test_inner_command_rejects_unknown_tool():
    """Given an unknown tool, When building a command, Then it raises ValueError."""
    m = _mod()
    with pytest.raises(ValueError):
        m._inner_command("flake8", ["apps/a.py"])


def test_remote_lint_cmd_uses_dell_context_volume_and_image():
    """Given a Dell slice, When building the remote command, Then it targets the dell context."""
    m = _mod()
    cmd = m._remote_lint_cmd("dell", "ruff", ["apps/a.py"])
    assert cmd[0] == "ssh"
    remote = cmd[-1]
    assert "docker run --rm" in remote
    assert "xf_lint_repo:/repo" in remote
    assert "DJANGO_SETTINGS_MODULE=config.settings.test" in remote
    assert "DJANGO_SECRET_KEY=ci-fake-secret-key" in remote
    assert "POSTGRES_PASSWORD=ci-fake-postgres-password" in remote
    assert "xf-linker-backend-quality:latest" in remote
    assert remote.endswith("ruff check apps/a.py")
    # cwd is the synced source on the remote, never the local /app bind mount.
    assert "/repo/backend" in remote


def test_remote_lint_cmd_mypy_execs_into_warm_dmypy_daemon():
    """Given a mypy slice, When building the remote command, Then it execs into the warm daemon container."""
    m = _mod()
    cmd = m._remote_lint_cmd("dell", "mypy", ["apps/a.py"])
    assert cmd[0] == "ssh"
    remote = cmd[-1]
    assert "docker exec xf-dmypy-daemon" in remote
    assert remote.endswith(
        "dmypy run --timeout 7200 -- --config-file /repo/backend/mypy.ini apps/a.py"
    )
    # the daemon must survive between runs — one-shot --rm is forbidden here.
    assert "--rm" not in remote


def test_remote_docker_cmd_quotes_as_one_ssh_command():
    """Given a shell-sensitive Docker command, When building it, Then SSH gets one command."""
    m = _mod()
    cmd = m._remote_docker_cmd("dell", "run", "alpine:latest", "sh", "-c", "echo ok")
    assert cmd[0] == "ssh"
    assert cmd[-1] == "docker run alpine:latest sh -c 'echo ok'"


def test_remote_docker_cmd_can_use_direct_local_docker():
    """Given Bazel is already running on Dell, When context is local, Then no SSH is used."""
    m = _mod()
    assert m._remote_docker_cmd("__local__", "info") == ["docker", "info"]


class _FakeProc:
    def __init__(self, rc: int, out: str = ""):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


def test_dmypy_daemon_container_is_reused(monkeypatch):
    """Given the daemon container already runs, When ensuring it, Then no new container is started."""
    m = _mod()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if "inspect" in " ".join(cmd):
            return _FakeProc(0, "true\n")
        return _FakeProc(0, "")

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    assert m._ensure_dmypy_container("dell") is None
    assert len(calls) == 1 and "inspect" in " ".join(calls[0])
    assert not any(" run -d" in " ".join(c) for c in calls)


def test_dmypy_daemon_container_is_started_when_absent(monkeypatch):
    """Given no running daemon container, When ensuring it, Then a fresh warm container is started."""
    m = _mod()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if "inspect" in " ".join(cmd):
            return _FakeProc(1, "Error: no such container\n")
        return _FakeProc(0, "")

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    assert m._ensure_dmypy_container("dell") is None
    removed = next(c for c in calls if "docker rm -f xf-dmypy-daemon" in " ".join(c))
    assert "xf-dmypy-daemon" in " ".join(removed)
    started = next(c for c in calls if "docker run -d" in " ".join(c))
    started_text = " ".join(started)
    assert "--name xf-dmypy-daemon" in started_text
    assert "--restart unless-stopped" in started_text
    assert "xf_lint_repo:/repo" in started_text
    assert started_text.endswith("sleep infinity")


def test_lint_slice_fails_closed_when_dmypy_daemon_cannot_start(monkeypatch):
    """Given the daemon cannot start, When linting mypy on Dell, Then the slice fails closed (no local fallback)."""
    m = _mod()
    monkeypatch.setattr(m, "_sync_source_to_context", lambda ctx, env: None)
    monkeypatch.setattr(m, "_run_remote_sha", lambda ctx, env: (lambda s: (0, "")))
    monkeypatch.setattr(m, "_verify_snapshot", lambda rr, files, hashes: True)
    monkeypatch.setattr(m, "_ensure_dmypy_container", lambda ctx: "daemon could not start")

    rc, out = m._lint_slice_on_remote("dell", "mypy", ["apps/a.py"])

    assert rc == 1
    assert "daemon could not start" in out


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


def test_lint_routing_context_can_be_overridden_for_bazel_on_dell(monkeypatch):
    """Given Bazel already runs on Dell, When context is overridden, Then lint uses local Docker."""
    m = _mod()
    monkeypatch.setenv("XF_LINT_DOCKER_CONTEXT", "__local__")
    machines = m._load_lint_routing_config()["machines"]
    assert machines[0]["context"] == "__local__"


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

    rc = m.run_lint(["ruff", "mypy"], ["apps/a.py", "apps/b.py"], evidence_out=ev)

    assert rc == 0
    rows = [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {r["tool_name"] for r in rows} == {"ruff", "mypy"}
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


def test_pip_audit_all_ignored_exit_code_is_treated_as_clean():
    """Given pip-audit found only ignored findings, When checking rc, Then it passes."""
    m = _mod()
    out = "Found 2 known vulnerabilities, ignored 2 in 1 package"

    assert m._dependency_audit_effective_rc("pip-audit", 1, out) == 0
    assert m._dependency_audit_effective_rc(
        "pip-audit",
        1,
        "Found 2 known vulnerabilities",
    ) == 1


def test_dependency_audit_runs_tools_and_records_evidence(monkeypatch, tmp_path):
    """Given --dependency-audit, When run, Then it executes pip-audit and safety check on Dell and logs evidence."""
    m = _mod()
    monkeypatch.setenv("XF_QUALITY_CACHE", "0")  # never touch the real pass-cache
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

    assert any("pip-audit" in " ".join(cmd) for cmd in ran_cmds)
    assert any("safety" in " ".join(cmd) for cmd in ran_cmds)
    
    rows = [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {r["tool_name"] for r in rows} == {"pip-audit", "safety"}
    assert all(r["status"] == "passed" for r in rows)
    assert all(r["check_type"] == "security" for r in rows)
