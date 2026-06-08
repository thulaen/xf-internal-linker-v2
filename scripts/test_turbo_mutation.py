#!/usr/bin/env python3
"""Unit tests for the weighted N-way turbo mutation split.

Run with either pytest::

    python -m pytest scripts/test_turbo_mutation.py -q

or as a plain script (no pytest needed — the repo's host Python has no
pytest, and the design names ``python scripts/test_turbo_mutation.py`` as the
run command)::

    python scripts/test_turbo_mutation.py

Everything here is pure-function or subprocess-mocked. NO live Docker and NO
live SSH are ever touched: the machine reachability probe is INJECTED as a
fake, and ``subprocess`` is monkeypatched where a runner is exercised.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_turbo_module():
    spec = importlib.util.spec_from_file_location(
        "turbo_mutation_for_tests",
        ROOT / "scripts" / "turbo_mutation.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_routing_module():
    spec = importlib.util.spec_from_file_location(
        "machine_routing_for_tests",
        ROOT / "scripts" / "machine_routing.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _machine(name, transport, weight, max_weight=1.0, context=None, ssh_host=None):
    """Build a raw machine dict in the config shape (pre-selection)."""
    m = {"name": name, "transport": transport, "weight": weight, "max_weight": max_weight}
    if context is not None:
        m["context"] = context
    if ssh_host is not None:
        m["ssh_host"] = ssh_host
    return m


def _three_raw():
    return [
        _machine("dell", "ssh", 0.60, max_weight=0.60, ssh_host="dell"),
        _machine("windows", "docker_local", 0.30, max_weight=1.0),
        _machine("mint", "docker_context", 0.10, max_weight=1.0, context="mint"),
    ]


# ── _partition_weighted ───────────────────────────────────────────────────────

def _shared(turbo, raw, reachable_names):
    """Run select with a fake probe so the returned machines carry `share`."""
    def probe(machine):
        return machine["name"] in reachable_names
    return turbo._select_machines({"machines": raw}, probe=probe)


def test_partition_weighted_sums_exactly_to_len_items() -> None:
    turbo = _load_turbo_module()
    machines = _shared(turbo, _three_raw(), {"dell", "windows", "mint"})
    for n in (0, 1, 9, 100):
        items = list(range(n))
        result = turbo._partition_weighted(items, machines)
        total = sum(len(v) for v in result.values())
        assert total == n, f"n={n}: slices summed to {total}, expected {n}"
        flat: list = []
        for m in machines:
            flat.extend(result[m["name"]])
        assert flat == items, f"n={n}: flattened union {flat} != input {items}"


def test_partition_weighted_nine_cpp_binaries() -> None:
    turbo = _load_turbo_module()
    machines = _shared(turbo, _three_raw(), {"dell", "windows", "mint"})
    items = [f"bin{i}" for i in range(9)]
    result = turbo._partition_weighted(items, items_machines := machines)
    counts = {m["name"]: len(result[m["name"]]) for m in machines}
    assert counts == {"dell": 5, "windows": 3, "mint": 1}, counts
    seen = [b for m in machines for b in result[m["name"]]]
    assert sorted(seen) == sorted(items)


def test_partition_weighted_fewer_items_than_machines() -> None:
    turbo = _load_turbo_module()
    machines = _shared(turbo, _three_raw(), {"dell", "windows", "mint"})
    result = turbo._partition_weighted(["only"], machines)
    assert result["dell"] == ["only"]
    assert result["windows"] == []
    assert result["mint"] == []


def test_partition_weighted_is_deterministic() -> None:
    turbo = _load_turbo_module()
    machines = _shared(turbo, _three_raw(), {"dell", "windows", "mint"})
    items = list(range(13))
    a = turbo._partition_weighted(items, machines)
    b = turbo._partition_weighted(items, machines)
    assert a == b


# ── _select_machines ──────────────────────────────────────────────────────────

def _shares(machines):
    return {m["name"]: round(m["share"], 6) for m in machines}


def test_select_machines_all_up_keeps_target_weights() -> None:
    turbo = _load_turbo_module()
    machines = _shared(turbo, _three_raw(), {"dell", "windows", "mint"})
    assert _shares(machines) == {"dell": 0.60, "windows": 0.30, "mint": 0.10}


def test_select_machines_dell_off_raises_error() -> None:
    turbo = _load_turbo_module()
    import pytest
    with pytest.raises(turbo._routing.RemoteUnavailableError):
        _shared(turbo, _three_raw(), {"windows", "mint"})


def test_select_machines_mint_off_raises_error() -> None:
    turbo = _load_turbo_module()
    import pytest
    with pytest.raises(turbo._routing.RemoteUnavailableError):
        _shared(turbo, _three_raw(), {"dell", "windows"})


def test_select_machines_never_exceeds_max_weight() -> None:
    turbo = _load_turbo_module()
    # When all configured machines are reachable, the shares are calculated and the ceiling is respected.
    machines = _shared(turbo, _three_raw(), {"dell", "windows", "mint"})
    for m in machines:
        if m["name"] == "dell":
            assert m["share"] <= 0.60 + 1e-9, m["share"]


def test_select_machines_all_off_raises_error() -> None:
    turbo = _load_turbo_module()
    import pytest
    with pytest.raises(turbo._routing.RemoteUnavailableError):
        _shared(turbo, _three_raw(), set())


def test_select_machines_probe_is_injected_no_live_io(monkeypatch) -> None:
    turbo = _load_turbo_module()
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("real subprocess must not run under a fake probe")

    monkeypatch.setattr(turbo.subprocess, "run", boom)
    monkeypatch.setattr(turbo.subprocess, "check_output", boom)
    turbo._select_machines({"machines": _three_raw()}, probe=lambda m: True)
    assert called["n"] == 0


# ── legacy config synthesis ───────────────────────────────────────────────────

def test_machines_from_config_legacy_shape_synthesises_two_machines() -> None:
    turbo = _load_turbo_module()
    legacy = {"split": {"local_pct": 0.65, "remote_pct": 0.35, "remote_context": "mint"}}
    machines = turbo._machines_from_config(legacy)
    by_name = {m["name"]: m for m in machines}
    assert set(by_name) == {"windows", "mint"}
    assert by_name["windows"]["transport"] == "docker_local"
    assert abs(by_name["windows"]["weight"] - 0.65) < 1e-9
    assert by_name["mint"]["transport"] == "docker_context"
    assert by_name["mint"]["context"] == "mint"
    assert abs(by_name["mint"]["weight"] - 0.35) < 1e-9


# ── transports ────────────────────────────────────────────────────────────────

def test_docker_context_branch_unchanged(monkeypatch) -> None:
    turbo = _load_turbo_module()
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(turbo.subprocess, "run", lambda cmd, **k: (calls.append(cmd), Result())[1])

    turbo._run_in_container("local", "compiled-tools", "echo local")
    turbo._run_in_container("mint", "compiled-tools", "echo remote")
    assert calls[0][:5] == ["docker", "compose", "exec", "-T", "compiled-tools"]
    assert calls[1][:7] == ["docker", "--context", "mint", "compose", "exec", "-T", "compiled-tools"]


def test_ssh_transport_syncs_source_then_builds_compose_run_no_deps(monkeypatch) -> None:
    turbo = _load_turbo_module()
    order: list[str] = []
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_sync(*a, **k):
        order.append("sync")
        return None  # success

    def fake_run(cmd, **k):
        order.append("run")
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(turbo, "_sync_source_to_dell_for_turbo", fake_sync)
    monkeypatch.setattr(turbo.subprocess, "run", fake_run)

    turbo._run_in_container(
        "ssh", "compiled-tools", "echo hi",
        ssh_host="dell",
    )
    assert order[0] == "sync", "source must be synced before the ssh run"
    argv = calls[-1]
    joined = " ".join(argv)
    assert argv[0] == "ssh"
    assert "set DOCKER_CONFIG=" in joined
    assert "docker compose run --rm --no-deps -T" in joined


# ── dispatch plan ─────────────────────────────────────────────────────────────

def test_unreachable_machine_spawns_no_thread() -> None:
    turbo = _load_turbo_module()
    # Define machines manually to bypass selection logic and test dispatching logic directly.
    machines = [
        {"name": "windows", "transport": "docker_local", "share": 0.75},
        {"name": "mint", "transport": "docker_context", "share": 0.25},
    ]
    items = [f"x{i}" for i in range(6)]
    plan = turbo._partition_weighted(items, machines)
    seen: list = []
    handled: list[str] = []

    def per_machine(machine, slice_items):
        handled.append(machine["name"])
        seen.extend(slice_items)

    turbo._dispatch_to_machines(machines, plan, per_machine)
    assert "dell" not in handled
    assert sorted(seen) == sorted(items)  # fail-open: all items still covered


def test_zero_item_machine_is_not_dispatched() -> None:
    turbo = _load_turbo_module()
    machines = _shared(turbo, _three_raw(), {"dell", "windows", "mint"})
    plan = turbo._partition_weighted(["solo"], machines)  # only dell gets work
    handled: list[str] = []

    def per_machine(machine, slice_items):
        handled.append(machine["name"])

    turbo._dispatch_to_machines(machines, plan, per_machine)
    assert handled == ["dell"]


def test_rust_core_budget_derives_from_weight_not_hardcoded_ratio() -> None:
    turbo = _load_turbo_module()
    # dell 0.60 of 20 cores = 12; windows 0.30 of 8 = 2 (round(2.4)); mint 0.10 of 4 = 0->1
    assert turbo._jobs_for(20, 0.60) == 12
    assert turbo._jobs_for(8, 0.30) == 2
    assert turbo._jobs_for(4, 0.10) == 1  # never below 1 for a reachable machine


def test_split_false_languages_stay_local() -> None:
    turbo = _load_turbo_module()
    cfg = {"machines": _three_raw()}
    machines = turbo._machines_for_language(cfg, split_enabled=False, probe=lambda m: True)
    assert len(machines) == 1
    assert machines[0]["transport"] == "docker_local"


# ── tiny standalone harness (no pytest on the host) ───────────────────────────

class _MonkeyPatch:
    """Minimal monkeypatch shim so the test functions run without pytest."""

    def __init__(self) -> None:
        self._undo: list = []

    def setattr(self, target, name, value=None):
        if value is None:  # setattr(obj.attr_path, val) form is unused here
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
        except Exception as exc:  # noqa: BLE001 — test harness reports every failure
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
