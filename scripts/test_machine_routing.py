#!/usr/bin/env python3
"""Unit tests for the shared machine-routing module.

These are the pure routing functions (machine selection + weighted partition)
that BOTH ``scripts/turbo_mutation.py`` (the big sweep) and
``.githooks/check-scoped-mutation.py`` (the per-commit gate) import, so the
weighting math lives in exactly one place.

Run as a plain script (the host has no pytest)::

    python scripts/test_machine_routing.py

Everything is pure-function or probe-injected. NO live Docker and NO live SSH
are ever touched: the reachability probe is INJECTED as a fake and the real
``subprocess`` is monkeypatched to RAISE so any accidental live call fails loud.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_routing():
    spec = importlib.util.spec_from_file_location(
        "machine_routing_for_tests", ROOT / "scripts" / "machine_routing.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_turbo():
    spec = importlib.util.spec_from_file_location(
        "turbo_mutation_for_routing_tests", ROOT / "scripts" / "turbo_mutation.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _machine(name, transport, weight, max_weight=1.0, context=None, ssh_host=None):
    m = {"name": name, "transport": transport, "weight": weight, "max_weight": max_weight}
    if context is not None:
        m["context"] = context
    if ssh_host is not None:
        m["ssh_host"] = ssh_host
    return m


def _three_raw():
    return [
        _machine("dell", "docker_context", 0.60, max_weight=0.60, context="dell"),
        _machine("windows", "docker_local", 0.30, max_weight=1.0),
        _machine("mint", "docker_context", 0.10, max_weight=1.0, context="mint"),
    ]


def _shared(routing, raw, reachable_names):
    return routing._select_machines(
        {"machines": raw}, probe=lambda m: m["name"] in reachable_names
    )


def _shares(machines):
    return {m["name"]: round(m["share"], 6) for m in machines}


# ── partition ──────────────────────────────────────────────────────────────────

def test_partition_sums_exactly_to_len_items() -> None:
    routing = _load_routing()
    machines = _shared(routing, _three_raw(), {"dell", "windows", "mint"})
    for n in (0, 1, 9, 100):
        items = list(range(n))
        result = routing._partition_weighted(items, machines)
        total = sum(len(v) for v in result.values())
        assert total == n, f"n={n}: summed to {total}"


def test_partition_nine_files_split_5_3_1() -> None:
    routing = _load_routing()
    machines = _shared(routing, _three_raw(), {"dell", "windows", "mint"})
    items = [f"f{i}" for i in range(9)]
    result = routing._partition_weighted(items, machines)
    counts = {m["name"]: len(result[m["name"]]) for m in machines}
    assert counts == {"dell": 5, "windows": 3, "mint": 1}, counts


# ── selection ──────────────────────────────────────────────────────────────────

def test_select_all_up() -> None:
    routing = _load_routing()
    machines = _shared(routing, _three_raw(), {"dell", "windows", "mint"})
    assert _shares(machines) == {"dell": 0.60, "windows": 0.30, "mint": 0.10}


def test_select_dell_off_raises_fail_closed() -> None:
    # Fail-CLOSED: a down remote (Dell) must NOT have its share moved to Windows.
    routing = _load_routing()
    try:
        _shared(routing, _three_raw(), {"windows", "mint"})
    except routing.RemoteUnavailableError as exc:
        assert "dell" in str(exc).lower()
        return
    raise AssertionError("expected RemoteUnavailableError when Dell is unreachable")


def test_select_any_remote_off_raises_fail_closed() -> None:
    # Even with Dell up, a different down remote (mint) hard-fails — Windows
    # never absorbs a dead remote's work.
    routing = _load_routing()
    try:
        _shared(routing, _three_raw(), {"dell", "windows"})
    except routing.RemoteUnavailableError:
        return
    raise AssertionError("expected RemoteUnavailableError when a remote is unreachable")


def test_renormalise_respects_dell_ceiling_when_clamped() -> None:
    # Keep ceiling-clamp coverage now that the partial-survivor path raises:
    # Dell weight 0.95 exceeds its 0.92 ceiling → clamped; Windows takes the rest.
    routing = _load_routing()
    machines = [
        {"name": "dell", "weight": 0.95, "max_weight": 0.92},
        {"name": "windows", "weight": 0.05, "max_weight": 1.0},
    ]
    routing._renormalise_with_ceilings(machines)
    shares = {m["name"]: round(m["share"], 6) for m in machines}
    assert shares["dell"] <= 0.92 + 1e-6, shares
    assert abs(shares["dell"] + shares["windows"] - 1.0) < 1e-9, shares


def test_select_all_off_raises_fail_closed() -> None:
    routing = _load_routing()
    try:
        _shared(routing, _three_raw(), set())
    except routing.RemoteUnavailableError:
        return
    raise AssertionError("expected RemoteUnavailableError when nothing is reachable")


def test_probe_injected_no_live_io(monkeypatch) -> None:
    routing = _load_routing()
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("real subprocess must not run under a fake probe")

    monkeypatch.setattr(routing.subprocess, "run", boom)
    monkeypatch.setattr(routing.subprocess, "check_output", boom)
    routing._select_machines({"machines": _three_raw()}, probe=lambda m: True)
    assert called["n"] == 0


# ── reachability probe (real exit-code handling) ───────────────────────────────

def _fake_proc(rc):
    class _P:
        returncode = rc
        stdout = b""
        stderr = b""
    return lambda *a, **k: _P()


def test_ssh_probe_windows_host_unknown_true_is_reachable(monkeypatch) -> None:
    # Tests SSH transport probe function: a Windows cmd.exe host returns 1 for
    # the unknown `true` command — NOT 255. That means SSH connected, so the
    # host MUST count as reachable. (Regression: the old `rc==0` check silently
    # dropped the machine on every commit.)
    routing = _load_routing()
    monkeypatch.setattr(routing.subprocess, "run", _fake_proc(1))
    assert routing._probe_reachable(
        {"name": "dell", "transport": "ssh", "ssh_host": "dell"}
    ) is True


def test_ssh_probe_connection_failure_255_is_unreachable(monkeypatch) -> None:
    # Tests SSH transport probe function: SSH uses 255 exclusively for its own
    # connection/auth failure → host down.
    routing = _load_routing()
    monkeypatch.setattr(routing.subprocess, "run", _fake_proc(255))
    assert routing._probe_reachable(
        {"name": "dell", "transport": "ssh", "ssh_host": "dell"}
    ) is False


def test_docker_probe_still_requires_rc_zero(monkeypatch) -> None:
    # Docker transports keep strict rc==0 (a non-zero `docker info` = not usable).
    routing = _load_routing()
    monkeypatch.setattr(routing.subprocess, "run", _fake_proc(1))
    assert routing._probe_reachable(
        {"name": "mint", "transport": "docker_context", "context": "mint"}
    ) is False
    monkeypatch.setattr(routing.subprocess, "run", _fake_proc(0))
    assert routing._probe_reachable(
        {"name": "windows", "transport": "docker_local"}
    ) is True


# ── coverage: legacy config path ───────────────────────────────────────────────

def test_legacy_config_without_machines_key() -> None:
    # lines 49-51: backward-compat path when config has only the old `split` dict
    routing = _load_routing()
    cfg = {"split": {"local_pct": 0.60, "remote_pct": 0.40, "remote_context": "mint"}}
    machines = routing._machines_from_config(cfg)
    assert len(machines) == 2
    names = {m["name"] for m in machines}
    assert names == {"windows", "mint"}
    win = next(m for m in machines if m["name"] == "windows")
    assert win["weight"] == 0.60


def test_legacy_config_defaults_when_split_key_absent() -> None:
    # lines 49-55: split key missing → defaults (0.65 / 0.35)
    routing = _load_routing()
    machines = routing._machines_from_config({})
    assert len(machines) == 2
    win = next(m for m in machines if m["name"] == "windows")
    assert win["weight"] == 0.65


# ── coverage: probe edge-cases ──────────────────────────────────────────────────

def test_probe_unknown_transport_is_unreachable() -> None:
    # line 124: else: return False for unrecognised transport type
    routing = _load_routing()
    assert routing._probe_reachable({"name": "x", "transport": "ftp"}) is False


def test_probe_subprocess_exception_is_unreachable(monkeypatch) -> None:
    # lines 137-138: except Exception → return False (e.g. OSError, permission denied)
    routing = _load_routing()
    def boom(*a, **k):
        raise OSError("network unreachable")
    monkeypatch.setattr(routing.subprocess, "run", boom)
    assert routing._probe_reachable(
        {"name": "mint", "transport": "docker_context", "context": "mint"}
    ) is False


def test_select_machines_default_probe_is_used_when_none_passed(monkeypatch) -> None:
    # line 100: probe = _probe_reachable is assigned when caller omits probe kwarg
    routing = _load_routing()
    # docker info returns 0 → reachable; only local machine in config so one survives
    monkeypatch.setattr(routing.subprocess, "run", _fake_proc(0))
    cfg = {"machines": [
        {"name": "windows", "transport": "docker_local", "weight": 1.0, "max_weight": 1.0},
    ]}
    machines = routing._select_machines(cfg)  # no probe= → uses the real _probe_reachable
    assert len(machines) == 1
    assert machines[0]["name"] == "windows"


# ── coverage: dispatch threading ────────────────────────────────────────────────

def test_dispatch_runs_per_machine_for_every_non_empty_slice() -> None:
    # lines 172-183: threading body — real dispatch, not mocked
    routing = _load_routing()
    calls: dict = {}
    lock = __import__("threading").Lock()

    def per_machine(machine, files):
        with lock:
            calls[machine["name"]] = list(files)

    machines = [
        {"name": "a", "transport": "docker_local", "share": 0.6},
        {"name": "b", "transport": "docker_local", "share": 0.4},
    ]
    plan = {"a": ["f1", "f2"], "b": ["f3"]}
    routing._dispatch_to_machines(machines, plan, per_machine)
    assert calls == {"a": ["f1", "f2"], "b": ["f3"]}


def test_dispatch_skips_machine_with_empty_slice() -> None:
    # line 178: empty-slice → no thread, no call
    routing = _load_routing()
    calls: dict = {}

    def per_machine(machine, files):
        calls[machine["name"]] = list(files)

    machines = [
        {"name": "a", "transport": "docker_local", "share": 0.7},
        {"name": "b", "transport": "docker_local", "share": 0.3},
    ]
    routing._dispatch_to_machines(machines, {"a": ["f1"], "b": []}, per_machine)
    assert "a" in calls
    assert "b" not in calls   # b got an empty slice → thread must not have spawned


# ── single-sourcing proof ──────────────────────────────────────────────────────

def test_turbo_reexports_same_object() -> None:
    # turbo re-exports from the routing module it loads itself; assert turbo's
    # public names ARE that module's functions (single-sourced, no copy).
    turbo = _load_turbo()
    routing = turbo._routing
    assert turbo._select_machines is routing._select_machines
    assert turbo._partition_weighted is routing._partition_weighted
    assert turbo._renormalise_with_ceilings is routing._renormalise_with_ceilings


# ── standalone harness (no pytest on the host) ─────────────────────────────────

class _MonkeyPatch:
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


def test_local_docker_context_is_rejected_on_windows_host(monkeypatch) -> None:
    """Tests/mutation must never target the local Docker Desktop engine on
    the Windows host (MSI) — even when a config points a docker_context
    machine at it."""
    routing = _load_routing()
    monkeypatch.setattr(routing, "_on_windows_host", lambda: True)
    cfg = {"machines": [
        _machine("sneaky-local", "docker_context", 1.0, context="desktop-linux"),
    ]}
    try:
        routing._select_machines(cfg, probe=lambda m: True)
    except routing.RemoteUnavailableError as exc:
        assert "blocked on this Windows machine" in str(exc)
        assert "Dell" in str(exc)
    else:
        raise AssertionError("desktop-linux context must be rejected on MSI")


def test_dell_context_is_allowed_on_windows_host(monkeypatch) -> None:
    routing = _load_routing()
    monkeypatch.setattr(routing, "_on_windows_host", lambda: True)
    cfg = {"machines": [_machine("dell", "docker_context", 1.0, context="dell")]}
    machines = routing._select_machines(cfg, probe=lambda m: True)
    assert [m["name"] for m in machines] == ["dell"]


def test_windows_host_detection_exempts_ci(monkeypatch) -> None:
    routing = _load_routing()
    monkeypatch.setattr(routing.os, "environ", {"GITHUB_ACTIONS": "true"})
    assert routing._on_windows_host() is False


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
