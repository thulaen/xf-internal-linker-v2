"""Unit tests for scripts/run_pytest_on_context.py (no Docker required).

Covers the pure, machine-independent logic: the remote/local docker command
construction (Dell joins its test-stack network + overrides DB/Redis hosts), the
routing-config read, and the split-and-merge verdict. The two slice runners are
monkeypatched so no container ever starts under test.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    import importlib.util

    path = ROOT / "scripts" / "run_pytest_on_context.py"
    spec = importlib.util.spec_from_file_location("run_pytest_on_context", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_remote_pytest_cmd_joins_dell_test_net_and_overrides_db_host():
    """Given a Dell slice, When building the command, Then it joins the test net and
    points the DB/Redis at Dell's own stack — never the live database."""
    m = _mod()
    cmd = m._remote_pytest_cmd("dell", ["apps/foo/tests.py"])
    assert cmd[:5] == ["docker", "--context", "dell", "run", "--rm"]
    assert "--network" in cmd and "xf_dell_test_net" in cmd
    assert "xf_test_repo:/repo" in cmd
    # DB + Redis point at Dell's test-stack service names, not the live host.
    assert "POSTGRES_HOST=postgres" in cmd
    assert "REDIS_URL=redis://redis:6379/0" in cmd
    assert "config.settings.test" in " ".join(cmd)
    assert cmd[-1] == "apps/foo/tests.py"
    assert "--reuse-db" in cmd


def test_local_pytest_cmd_uses_compose_backend_quality():
    """Given a local slice, When building the command, Then it runs compose backend-quality."""
    m = _mod()
    cmd = m._local_pytest_cmd(["apps/foo/tests.py"])
    assert cmd[:5] == ["docker", "compose", "run", "--rm", "-T"]
    assert "backend-quality" in cmd
    assert cmd[-1] == "apps/foo/tests.py"
    assert "--reuse-db" in cmd


def test_pytest_routing_config_puts_88_percent_on_dell():
    """Given the routing config, When read, Then Dell carries 88% of pytest."""
    m = _mod()
    machines = {entry["name"]: entry for entry in m._load_pytest_routing_config()["machines"]}
    assert machines["dell"]["weight"] == 0.88
    assert machines["dell"]["context"] == "dell"
    assert machines["windows"]["transport"] == "docker_local"
    cfg = json.loads((ROOT / "config" / "mutation-routing.json").read_text(encoding="utf-8"))
    assert cfg["pytest_machines"][0]["name"] == "dell"
    assert cfg["pytest_machines"][0]["weight"] == 0.88


def test_run_pytest_sharded_no_targets_is_clean():
    """Given no targets, When running, Then the verdict is a clean no-op."""
    m = _mod()
    rc, out = m.run_pytest_sharded([])
    assert rc == 0
    assert "no changed test targets" in out


def _fake_routing():
    """A stand-in for machine_routing with two machines and real split/dispatch."""
    class _R:
        @staticmethod
        def _select_machines(_cfg):
            return [
                {"name": "dell", "transport": "docker_context", "context": "dell", "share": 0.5},
                {"name": "windows", "transport": "docker_local", "share": 0.5},
            ]

        @staticmethod
        def _partition_weighted(items, machines):
            half = len(items) // 2
            return {"dell": items[:half], "windows": items[half:]}

        @staticmethod
        def _dispatch_to_machines(machines, plan, per_machine):
            for machine in machines:
                slice_items = plan.get(machine["name"]) or []
                if slice_items:
                    per_machine(machine, slice_items)

    return _R()


def test_run_pytest_sharded_merges_worst_rc(monkeypatch):
    """Given a Dell-pass / Windows-fail split, When merged, Then rc is the worst (fail)."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_pytest_slice_on_remote", lambda ctx, targets: (0, "dell ok\n"))
    monkeypatch.setattr(m, "_pytest_slice_local", lambda targets: (1, "FAILED test_x\n"))

    rc, out = m.run_pytest_sharded(["apps/a/tests.py", "apps/b/tests.py"])

    assert rc == 1
    assert "windows" in out
    assert "FAILED test_x" in out


def test_run_pytest_sharded_fails_open_to_local_when_remote_untrusted(monkeypatch):
    """Given Dell returns untrusted (None), When running, Then that slice re-runs locally."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_pytest_slice_on_remote", lambda ctx, targets: None)
    local_calls = []

    def _local(targets):
        local_calls.append(targets)
        return 0, "ok\n"

    monkeypatch.setattr(m, "_pytest_slice_local", _local)

    rc, _out = m.run_pytest_sharded(["apps/a/tests.py", "apps/b/tests.py"])

    assert rc == 0
    assert len(local_calls) == 2  # Dell's slice re-run locally + Windows' own slice


def test_main_writes_normal_test_evidence_row_when_requested(monkeypatch, tmp_path):
    """Given --evidence-out, When the pytest split runs, Then a passed normal_test row is written."""
    m = _mod()
    monkeypatch.setattr(m, "run_pytest_sharded", lambda targets: (0, "ok\n"))
    ev = tmp_path / "python.jsonl"

    rc = m.main(["--targets", "apps/a/tests.py", "--evidence-out", str(ev)])

    assert rc == 0
    rows = [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["tool_name"] == "pytest"
    assert rows[0]["check_type"] == "normal_test"
    assert rows[0]["status"] == "passed"


def test_main_records_failure_evidence_when_split_fails(monkeypatch, tmp_path):
    """Given a failing pytest split, When --evidence-out is set, Then a failed row is written."""
    m = _mod()
    monkeypatch.setattr(m, "run_pytest_sharded", lambda targets: (1, "FAILED\n"))
    ev = tmp_path / "python.jsonl"

    rc = m.main(["--targets", "apps/a/tests.py", "--evidence-out", str(ev)])

    assert rc == 1
    rows = [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["status"] == "failed"
    assert rows[0]["failure_fingerprint"] == "pytest:1"
