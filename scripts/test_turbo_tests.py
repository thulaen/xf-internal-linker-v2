#!/usr/bin/env python3
"""Unit tests for scripts/turbo_tests.py.

Run as a plain script (the repo's host Python has no pytest)::

    python scripts/test_turbo_tests.py

or with pytest::

    python -m pytest scripts/test_turbo_tests.py -q

All subprocess calls are mocked.  No live Docker and no live SSH are ever
touched.  The module under test is loaded by absolute path via importlib so
the tests work without installing anything.

API contract under test
-----------------------
``_run_shard_local(files, cmd_template)``
    Run a test shard locally in the backend container.
    Returns ``(rc: int, output: str)``.

``_run_shard_context(files, cmd_template, context)``
    Sync source to the remote Docker context, then run the shard.
    Returns ``(rc: int, output: str)``.  If the sync step returns a non-None
    string the function returns ``(1, error_string)`` without calling subprocess.

``_run_shard_on_machine(machine, files, cmd_template)``
    Dispatch to ``_run_shard_local`` or ``_run_shard_context`` based on
    ``machine["transport"]``.  Unknown transports return ``(1, "Unknown...")``.

``_merge_shard_results(results)``
    Accept a list of ``{"machine": dict, "rc": int|None, "output": str}`` dicts.
    Entries with ``rc=None`` are treated as un-executed and are re-run locally
    via ``_run_shard_local``.  Returns overall ``rc`` (0 if ALL pass, 1 if ANY
    fail, including local re-run failures).

``_collect_simpletest_files(paths)``
    Return the list of Python test-module paths discovered under ``paths``.
    (May call ``subprocess`` internally but is mocked here.)

``run_python_tests(machines, paths)``
    Orchestrate the full Django-test run across the given machines.
    Calls ``_collect_simpletest_files`` first; returns 0 with no dispatching
    when the list is empty.  Otherwise partitions files by machine weight and
    dispatches.  Returns 0 if all shards pass, 1 otherwise.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ── module loader ─────────────────────────────────────────────────────────────

def _load_turbo_tests():
    spec = importlib.util.spec_from_file_location(
        "turbo_tests_for_tests",
        ROOT / "scripts" / "turbo_tests.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── helpers ───────────────────────────────────────────────────────────────────

def _machine(name, transport, weight=1.0, share=1.0, context=None):
    m = {"name": name, "transport": transport, "weight": weight, "share": share}
    if context is not None:
        m["context"] = context
    return m


def _local_machine():
    return _machine("windows", "docker_local", weight=1.0, share=1.0)


def _context_machine(name="mint", context="mint"):
    return _machine(name, "docker_context", weight=0.35, share=0.35, context=context)


class _FakeResult:
    """Simulates subprocess.CompletedProcess."""

    def __init__(self, rc: int, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


# ── _run_shard_local ──────────────────────────────────────────────────────────

def test_run_shard_local_rc0_returns_zero_and_has_pytest_in_cmd(monkeypatch) -> None:
    tt = _load_turbo_tests()
    captured: list = []

    def fake_run(cmd, **k):
        captured.append(cmd)
        return _FakeResult(0, stdout="passed")

    monkeypatch.setattr(tt.subprocess, "run", fake_run)

    rc, output = tt._run_shard_local(
        ["backend/apps/foo/tests.py"], "pytest {files}"
    )

    assert rc == 0, f"expected rc=0, got {rc}"
    assert len(captured) == 1, "subprocess.run should be called exactly once"
    joined = " ".join(captured[0])
    assert "pytest" in joined, f"'pytest' not found in cmd: {captured[0]}"


def test_run_shard_local_rc1_returns_one(monkeypatch) -> None:
    tt = _load_turbo_tests()

    monkeypatch.setattr(
        tt.subprocess, "run",
        lambda cmd, **k: _FakeResult(1, stdout="", stderr="FAILED 1 test"),
    )

    rc, output = tt._run_shard_local(
        ["backend/apps/bar/tests.py"], "pytest {files}"
    )

    assert rc == 1, f"expected rc=1, got {rc}"


# ── _run_shard_context ────────────────────────────────────────────────────────

def test_run_shard_context_sync_ok_subprocess_rc0_returns_zero(monkeypatch) -> None:
    tt = _load_turbo_tests()
    subprocess_called: list[bool] = []

    monkeypatch.setattr(tt, "_sync_test_source_to_context", lambda ctx: None)
    monkeypatch.setattr(
        tt.subprocess, "run",
        lambda cmd, **k: (subprocess_called.append(True), _FakeResult(0, "ok"))[1],
    )

    rc, output = tt._run_shard_context(
        ["backend/apps/baz/tests.py"], "pytest {files}", context="mint"
    )

    assert rc == 0, f"expected rc=0, got {rc}"
    assert subprocess_called, "subprocess.run must be called when sync succeeds"


def test_run_shard_context_sync_error_returns_1_without_subprocess(monkeypatch) -> None:
    tt = _load_turbo_tests()
    subprocess_called: list[bool] = []

    monkeypatch.setattr(
        tt, "_sync_test_source_to_context",
        lambda ctx: "rsync failed: connection refused",
    )
    monkeypatch.setattr(
        tt.subprocess, "run",
        lambda cmd, **k: (subprocess_called.append(True), _FakeResult(0))[1],
    )

    rc, output = tt._run_shard_context(
        ["backend/apps/baz/tests.py"], "pytest {files}", context="mint"
    )

    assert rc == 1, f"expected rc=1 when sync fails, got {rc}"
    assert not subprocess_called, "subprocess must NOT be called when sync fails"
    assert "rsync failed" in output or len(output) > 0, (
        "error string from sync should appear in output"
    )


# ── _run_shard_on_machine ─────────────────────────────────────────────────────

def test_run_shard_on_machine_docker_local_calls_only_run_shard_local(monkeypatch) -> None:
    tt = _load_turbo_tests()
    calls: list[str] = []

    monkeypatch.setattr(
        tt, "_run_shard_local",
        lambda files, cmd: (calls.append("local"), (0, "ok"))[1],
    )
    monkeypatch.setattr(
        tt, "_run_shard_context",
        lambda files, cmd, context: (calls.append("context"), (0, "ok"))[1],
    )

    rc, _ = tt._run_shard_on_machine(
        _local_machine(), ["apps/foo/tests.py"], "pytest {files}"
    )

    assert calls == ["local"], f"expected only local call, got: {calls}"
    assert rc == 0


def test_run_shard_on_machine_docker_context_calls_only_run_shard_context(monkeypatch) -> None:
    tt = _load_turbo_tests()
    calls: list[str] = []

    monkeypatch.setattr(
        tt, "_run_shard_local",
        lambda files, cmd: (calls.append("local"), (0, "ok"))[1],
    )
    monkeypatch.setattr(
        tt, "_run_shard_context",
        lambda files, cmd, context: (calls.append("context"), (0, "ok"))[1],
    )

    rc, _ = tt._run_shard_on_machine(
        _context_machine(), ["apps/baz/tests.py"], "pytest {files}"
    )

    assert calls == ["context"], f"expected only context call, got: {calls}"
    assert rc == 0


def test_run_shard_on_machine_unknown_transport_returns_1_with_message(monkeypatch) -> None:
    tt = _load_turbo_tests()

    # Neither helper should be called for an unknown transport.
    monkeypatch.setattr(tt, "_run_shard_local", lambda *a: (_ for _ in ()).throw(
        AssertionError("_run_shard_local must not be called for unknown transport")
    ))
    monkeypatch.setattr(tt, "_run_shard_context", lambda *a: (_ for _ in ()).throw(
        AssertionError("_run_shard_context must not be called for unknown transport")
    ))

    unknown_machine = _machine("oddbox", "ftp_push", weight=0.5, share=0.5)
    rc, output = tt._run_shard_on_machine(
        unknown_machine, ["apps/foo/tests.py"], "pytest {files}"
    )

    assert rc == 1, f"expected rc=1 for unknown transport, got {rc}"
    assert "Unknown" in output or "unknown" in output.lower(), (
        f"expected 'Unknown' in error output, got: {output!r}"
    )


# ── _merge_shard_results ──────────────────────────────────────────────────────

def test_merge_shard_results_all_pass_returns_rc0() -> None:
    tt = _load_turbo_tests()
    results = [
        {"machine": _local_machine(),    "rc": 0, "output": "ok"},
        {"machine": _context_machine(),  "rc": 0, "output": "ok"},
    ]
    rc = tt._merge_shard_results(results)
    assert rc == 0, f"expected rc=0 when all shards pass, got {rc}"


def test_merge_shard_results_any_fail_returns_rc1() -> None:
    tt = _load_turbo_tests()
    results = [
        {"machine": _local_machine(),   "rc": 0, "output": "ok"},
        {"machine": _context_machine(), "rc": 1, "output": "FAILED"},
    ]
    rc = tt._merge_shard_results(results)
    assert rc == 1, f"expected rc=1 when any shard fails, got {rc}"


def test_merge_shard_results_none_rc_reruns_locally(monkeypatch) -> None:
    tt = _load_turbo_tests()
    rerun_calls: list = []

    def fake_local(files, cmd):
        rerun_calls.append(files)
        return (0, "rerun ok")

    monkeypatch.setattr(tt, "_run_shard_local", fake_local)

    results = [
        {"machine": _context_machine(), "rc": None, "output": "",
         "files": ["apps/baz/tests.py"], "cmd": "pytest {files}"},
    ]
    rc = tt._merge_shard_results(results)

    assert rerun_calls, "_run_shard_local must be called for rc=None entries"
    assert rc == 0, f"expected rc=0 when local re-run passes, got {rc}"


def test_merge_shard_results_none_rc_local_also_fails_returns_rc1(monkeypatch) -> None:
    tt = _load_turbo_tests()

    monkeypatch.setattr(tt, "_run_shard_local", lambda files, cmd: (1, "still failing"))

    results = [
        {"machine": _context_machine(), "rc": None, "output": "",
         "files": ["apps/baz/tests.py"], "cmd": "pytest {files}"},
    ]
    rc = tt._merge_shard_results(results)

    assert rc == 1, (
        f"expected rc=1 when both remote (None) and local re-run fail, got {rc}"
    )


# ── dry-run discovery ─────────────────────────────────────────────────────────

def test_discover_simpletest_files_fast_scans_without_subprocess(monkeypatch) -> None:
    tt = _load_turbo_tests()

    import tempfile

    with tempfile.TemporaryDirectory() as raw_root:
        repo_root = Path(raw_root)
        test_dir = repo_root / "backend" / "apps" / "example"
        test_dir.mkdir(parents=True)
        (test_dir / "tests_fast.py").write_text(
            "from django.test import SimpleTestCase\n\n"
            "class ExampleTests(SimpleTestCase):\n"
            "    pass\n",
            encoding="utf-8",
        )
        (test_dir / "test_db.py").write_text(
            "from django.test import TestCase\n\n"
            "class DbTests(TestCase):\n"
            "    pass\n",
            encoding="utf-8",
        )
        (test_dir / "helper.py").write_text("SimpleTestCase\n", encoding="utf-8")
        monkeypatch.setattr(tt, "REPO_ROOT", repo_root)
        monkeypatch.setattr(
            tt.subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("fast discovery must not call subprocess")
            ),
        )

        files = tt._discover_simpletest_files_fast()

    assert files == ["apps/example/tests_fast.py"]


def test_main_dry_run_uses_fast_discovery(monkeypatch) -> None:
    tt = _load_turbo_tests()

    class FakeRouting:
        class RemoteUnavailableError(RuntimeError):
            pass

        def _select_machines(self, cfg: dict[str, object]) -> list[dict[str, object]]:
            return [{"name": "dell"}, {"name": "windows"}]

        def _partition_weighted(
            self,
            files: list[str],
            machines: list[dict[str, object]],
        ) -> dict[str, list[str]]:
            return {
                str(machines[0]["name"]): files[:1],
                str(machines[1]["name"]): files[1:],
            }

    def fail_collect(paths: list[str] | None = None) -> list[str]:
        raise AssertionError("dry-run must not use Docker collection")

    monkeypatch.setattr(tt, "_load_routing_cfg", lambda: {"machines": []})
    monkeypatch.setattr(tt, "_load_machine_routing", lambda: FakeRouting())
    monkeypatch.setattr(
        tt,
        "_discover_simpletest_files_fast",
        lambda paths=None: ["apps/a/tests.py", "apps/b/tests.py"],
    )
    monkeypatch.setattr(tt, "_collect_simpletest_files", fail_collect)
    monkeypatch.setattr(
        tt.sys,
        "argv",
        ["turbo_tests.py", "--language", "python", "--dry-run"],
    )

    assert tt.main() == 0


def test_main_dry_run_reports_blocked_remote(monkeypatch) -> None:
    tt = _load_turbo_tests()

    class FakeRouting:
        class RemoteUnavailableError(RuntimeError):
            pass

        def _select_machines(self, cfg: dict[str, object]) -> list[dict[str, object]]:
            raise self.RemoteUnavailableError("Dell is not reachable")

    monkeypatch.setattr(tt, "_load_routing_cfg", lambda: {"machines": []})
    monkeypatch.setattr(tt, "_load_machine_routing", lambda: FakeRouting())
    monkeypatch.setattr(
        tt.sys,
        "argv",
        ["turbo_tests.py", "--language", "python", "--dry-run"],
    )

    assert tt.main() == 1


# ── run_python_tests ──────────────────────────────────────────────────────────

def test_run_python_tests_no_files_returns_0_without_dispatching(monkeypatch) -> None:
    tt = _load_turbo_tests()
    dispatched: list = []

    monkeypatch.setattr(tt, "_collect_simpletest_files", lambda paths: [])
    monkeypatch.setattr(
        tt, "_run_shard_on_machine",
        lambda machine, files, cmd: (dispatched.append(machine["name"]), (0, "ok"))[1],
    )

    rc = tt.run_python_tests(
        machines=[_local_machine(), _context_machine()],
        paths=["backend/apps"],
    )

    assert rc == 0, f"expected rc=0 for empty file list, got {rc}"
    assert not dispatched, "no dispatch should happen when there are no test files"


def test_run_python_tests_with_files_dispatches_per_machine_and_returns_0(monkeypatch) -> None:
    tt = _load_turbo_tests()
    dispatched_machines: list[str] = []

    test_files = [f"backend/apps/app{i}/tests.py" for i in range(6)]

    monkeypatch.setattr(tt, "_collect_simpletest_files", lambda paths: test_files)
    monkeypatch.setattr(
        tt, "_run_shard_on_machine",
        lambda machine, files, cmd: (
            dispatched_machines.append(machine["name"]),
            (0, "ok"),
        )[1],
    )
    monkeypatch.setattr(
        tt, "_merge_shard_results",
        lambda results: 0,
    )

    machines = [_local_machine(), _context_machine()]
    rc = tt.run_python_tests(machines=machines, paths=["backend/apps"])

    assert rc == 0, f"expected rc=0 when all shards pass, got {rc}"
    # At least one dispatch per reachable machine that received a non-empty slice.
    assert len(dispatched_machines) >= 1, (
        "expected at least one dispatch when test files are present"
    )


# ── standalone harness (no pytest on the host) ────────────────────────────────

class _MonkeyPatch:
    """Minimal monkeypatch shim so the test functions run without pytest."""

    def __init__(self) -> None:
        self._undo: list = []

    def setattr(self, target, name, value=None):
        if value is None:
            raise TypeError("use setattr(obj, name, value)")
        old = getattr(target, name)
        self._undo.append((target, name, old))
        setattr(target, name, value)

    def undo(self) -> None:
        for target, name, old in reversed(self._undo):
            setattr(target, name, old)
        self._undo.clear()


def _run_all() -> int:
    import inspect

    tests = sorted(
        (n, f) for n, f in globals().items()
        if n.startswith("test_") and inspect.isfunction(f)
    )
    failures: list[str] = []
    for name, fn in tests:
        mp = _MonkeyPatch()
        try:
            if "monkeypatch" in inspect.signature(fn).parameters:
                fn(mp)
            else:
                fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001 — harness reports every failure
            import traceback
            failures.append(name)
            print(f"FAIL {name}: {exc}")
            traceback.print_exc()
        finally:
            mp.undo()
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_run_all())
