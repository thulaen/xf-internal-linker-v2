"""Unit tests for scripts/run_pytest_on_context.py (no Docker required).

Covers the pure, machine-independent logic: the remote docker command
construction (Dell joins its test-stack network + overrides DB/Redis hosts), the
routing-config read, and the split-and-merge verdict. The slice runner is
monkeypatched so no container ever starts under test. Every target routes to a
docker_context machine — there is no local-Windows execution path left.
"""

import json
import inspect
from pathlib import Path
from types import SimpleNamespace

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
    assert "xf_dell_compiled_repo:/opt/xf/compiled" in cmd
    # DB + Redis point at Dell's test-stack service names, not the live host.
    assert "POSTGRES_HOST=postgres" in cmd
    assert "REDIS_URL=redis://redis:6379/0" in cmd
    assert "PYTHONPATH=/opt/xf/compiled/active:/opt/xf/compiled:/repo/backend" in cmd
    assert "config.settings.test" in " ".join(cmd)
    assert cmd[-1] == "apps/foo/tests.py"
    assert "--reuse-db" in cmd


def test_sync_roots_feed_the_tar_command_and_cover_test_reads():
    """_SYNC_ROOTS is the tar command's actual file list; it must cover every
    path the Dell-run script tests read (scripts, hooks, repo config)."""
    m = _mod()
    import inspect
    assert "*_SYNC_ROOTS" in inspect.getsource(m._tar_producer)
    for root in ("backend", "config", "scripts", ".githooks",
                 ".gitattributes", "docker-compose.yml"):
        assert root in m._SYNC_ROOTS, f"{root} must sync to Dell"
    assert "--exclude=backend/backups" in m._TAR_EXCLUDES


def test_host_hashes_strip_pytest_node_ids():
    """Given a single-test target, When hashing, Then only the file path is read."""
    m = _mod()
    hashes = m._host_hashes([
        "apps/auto_issues/tests_quality_evidence.py::ProtectedDataMapTests::test_one"
    ])
    assert "apps/auto_issues/tests_quality_evidence.py" in hashes


def test_sync_source_makes_audit_writable_for_dell_tests():
    """Given Dell tests write audit logs, When syncing, Then audit is writable."""
    m = _mod()
    source = inspect.getsource(m._sync_source_to_context)
    assert "mkdir -p /repo/audit" in source
    assert "chmod 777 /repo/audit" in source





def test_pytest_routing_config_puts_100_percent_on_dell():
    """Given the routing config, When read, Then Dell carries 100% of pytest and Windows 0% (fail-closed)."""
    m = _mod()
    machines = {entry["name"]: entry for entry in m._load_pytest_routing_config()["machines"]}
    assert machines["dell"]["weight"] == 1.0
    assert machines["dell"]["context"] == "dell"
    cfg = json.loads((ROOT / "config" / "mutation-routing.json").read_text(encoding="utf-8"))
    assert cfg["pytest_machines"][0]["name"] == "dell"
    assert cfg["pytest_machines"][0]["weight"] == 1.0


def test_no_local_only_carveout_remains():
    """Given the Dell-only router, When inspecting the module, Then the local-only
    target list and every local-execution helper are gone."""
    m = _mod()
    assert not hasattr(m, "_LOCAL_ONLY_TARGET_PARTS")
    assert not hasattr(m, "_is_local_only_target")
    assert not hasattr(m, "_split_local_only_targets")
    assert not hasattr(m, "_local_pytest_cmd")


def test_in_code_fallback_machines_are_all_docker_context(monkeypatch, tmp_path):
    """Given a broken routing config, When falling back, Then every fallback
    machine is a docker_context machine (no local Windows slice)."""
    m = _mod()
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)  # no config file -> in-code fallback
    machines = m._load_pytest_routing_config()["machines"]
    assert machines
    assert all(entry["transport"] == "docker_context" for entry in machines)
    assert all(entry["name"] != "windows" for entry in machines)


def test_every_target_lands_on_a_docker_context_machine(monkeypatch):
    """Given targets including the old local-only smoke test, When sharded, Then
    every target — including the faro smoke test — runs on the Dell context."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    seen: dict[str, list[str]] = {}

    def fake_slice(ctx, targets, cov_targets=None):
        seen[ctx] = list(targets)
        return 0, "ok\n"

    monkeypatch.setattr(m, "_pytest_slice_on_remote", fake_slice)

    targets = ["apps/observability/tests_faro_alloy_smoke.py", "apps/a/tests.py"]
    rc, _out = m.run_pytest_sharded(targets)

    assert rc == 0
    assert seen == {"dell": targets}


def test_cov_targets_add_cov_flags_to_remote_command():
    """Given --cov-targets values, When building the Dell command, Then a --cov
    flag per target plus a terminal coverage report are included."""
    m = _mod()
    cmd = m._remote_pytest_cmd(
        "dell", ["apps/foo/tests.py"], cov_targets=["apps.foo", "apps.bar"]
    )
    assert "--cov=apps.foo" in cmd
    assert "--cov=apps.bar" in cmd
    assert "--cov-report=term" in cmd
    assert cmd[-1] == "apps/foo/tests.py"
    # Without cov targets the command stays unchanged.
    plain = m._remote_pytest_cmd("dell", ["apps/foo/tests.py"])
    assert all(not part.startswith("--cov") for part in plain)


def test_main_threads_cov_targets_into_the_shard_runner(monkeypatch):
    """Given comma- and repeat-form --cov-targets, When main runs, Then the parsed
    list reaches run_pytest_sharded."""
    m = _mod()
    captured: dict[str, list[str]] = {}

    def fake_sharded(targets, cov_targets=None):
        captured["targets"] = list(targets)
        captured["cov"] = list(cov_targets or [])
        return 0, "ok\n"

    monkeypatch.setattr(m, "run_pytest_sharded", fake_sharded)
    monkeypatch.setenv("XF_QUALITY_CACHE", "0")  # isolate from the shared pass-cache
    rc = m.main([
        "--targets", "apps/a/tests.py",
        "--cov-targets", "apps.a,apps.b",
        "--cov-targets", "apps.c",
    ])

    assert rc == 0
    assert captured["cov"] == ["apps.a", "apps.b", "apps.c"]


def test_run_pytest_sharded_no_targets_is_clean():
    """Given no targets, When running, Then the verdict is a clean no-op."""
    m = _mod()
    rc, out = m.run_pytest_sharded([])
    assert rc == 0
    assert "no changed test targets" in out


def test_configure_stdout_uses_utf8_when_supported(monkeypatch):
    """Given Windows output may reject Unicode, When starting, Then stdout is UTF-8."""
    m = _mod()
    calls = []
    fake_stdout = SimpleNamespace(
        reconfigure=lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(m.sys, "stdout", fake_stdout)

    m._configure_stdout()

    assert calls == [{"encoding": "utf-8", "errors": "replace"}]


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


def test_run_pytest_sharded_merges_worst_rc(monkeypatch):
    """Given a Dell failure, When merged, Then rc is the worst (fail)."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_pytest_slice_on_remote", lambda ctx, targets, cov_targets=None: (1, "FAILED test_x\n"))

    rc, out = m.run_pytest_sharded(["apps/a/tests.py", "apps/b/tests.py"])

    assert rc == 1
    assert "dell" in out
    assert "FAILED test_x" in out


def test_run_pytest_sharded_fails_closed_when_remote_untrusted(monkeypatch):
    """Given Dell returns untrusted (None), When running, Then it fails closed."""
    m = _mod()
    monkeypatch.setattr(m, "_load_machine_routing", _fake_routing)
    monkeypatch.setattr(m, "_pytest_slice_on_remote", lambda ctx, targets, cov_targets=None: None)

    rc, out = m.run_pytest_sharded(["apps/a/tests.py", "apps/b/tests.py"])

    assert rc == 1
    assert "Dell source sync or manifest verification failed" in out


def test_run_pytest_sharded_fails_closed_for_non_docker_context(monkeypatch):
    """Given a non-docker_context machine, When running, Then it fails closed."""
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
    monkeypatch.setattr(m, "_pytest_slice_on_remote", lambda ctx, targets, cov_targets=None: (0, ""))

    rc, out = m.run_pytest_sharded(["apps/a/tests.py", "apps/b/tests.py"])

    assert rc == 1
    assert "transport not allowed" in out


def test_main_writes_normal_test_evidence_row_when_requested(monkeypatch, tmp_path):
    """Given --evidence-out, When the pytest split runs, Then a passed normal_test row is written."""
    m = _mod()
    monkeypatch.setattr(m, "run_pytest_sharded", lambda targets, cov_targets=None: (0, "ok\n"))
    monkeypatch.setenv("XF_QUALITY_CACHE", "0")  # isolate from the shared pass-cache
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
    monkeypatch.setattr(m, "run_pytest_sharded", lambda targets, cov_targets=None: (1, "FAILED\n"))
    monkeypatch.setenv("XF_QUALITY_CACHE", "0")  # isolate from the shared pass-cache
    ev = tmp_path / "python.jsonl"

    rc = m.main(["--targets", "apps/a/tests.py", "--evidence-out", str(ev)])

    assert rc == 1
    rows = [json.loads(line) for line in ev.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["status"] == "failed"
    assert rows[0]["failure_fingerprint"] == "pytest:1"


def test_load_cache_map_parses_selector_output(tmp_path):
    """Given the selector's --map-out JSON, When loading it, Then targets map to
    their source lists and malformed input degrades to an empty map."""
    m = _mod()
    good = tmp_path / "map.json"
    good.write_text(
        json.dumps({"apps/a/tests.py": ["apps/a/src.py"]}), encoding="utf-8"
    )
    assert m._load_cache_map(str(good)) == {"apps/a/tests.py": ["apps/a/src.py"]}
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all", encoding="utf-8")
    assert m._load_cache_map(str(bad)) == {}
    assert m._load_cache_map(None) == {}


def test_cache_map_reruns_target_when_a_mapped_source_changes(tmp_path, monkeypatch):
    """Given a cached pytest pass keyed with --cache-map, When only the SOURCE
    file changes, Then the target is re-run instead of cache-skipped."""
    m = _mod()
    (tmp_path / "audit").mkdir()
    test_file = tmp_path / "backend" / "apps" / "a" / "tests.py"
    src_file = tmp_path / "backend" / "apps" / "a" / "src.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    src_file.write_text("VALUE = 1\n", encoding="utf-8")
    cache_map = tmp_path / "map.json"
    cache_map.write_text(
        json.dumps({"apps/a/tests.py": ["apps/a/src.py"]}), encoding="utf-8"
    )
    runs: list[list[str]] = []

    def fake_sharded(targets, cov_targets=None):
        runs.append(list(targets))
        return 0, "ok\n"

    monkeypatch.setattr(m, "run_pytest_sharded", fake_sharded)
    monkeypatch.setattr(m, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("XF_QUALITY_CACHE", raising=False)
    argv = ["--targets", "apps/a/tests.py", "--cache-map", str(cache_map)]

    assert m.main(argv) == 0          # first run executes and records a pass
    assert m.main(argv) == 0          # unchanged content -> cache skip
    assert len(runs) == 1
    src_file.write_text("VALUE = 2\n", encoding="utf-8")
    assert m.main(argv) == 0          # source changed -> must re-run
    assert len(runs) == 2
