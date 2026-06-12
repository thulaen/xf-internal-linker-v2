#!/usr/bin/env python3
"""Shared machine-routing math for weighted N-way mutation work.

This tiny module is the SINGLE SOURCE of the machine-selection and
weighted-partition logic used by two callers:

* ``scripts/turbo_mutation.py`` — the big per-language mutation SWEEP.
* ``.githooks/check-scoped-mutation.py`` — the per-commit scoped-mutation GATE.

It has ZERO Django imports and does NOT import either caller, so it breaks the
import cycle (``turbo_mutation`` importlib-loads the gate for its SSH helpers, so
the gate cannot import ``turbo_mutation`` at top level). Both callers
importlib-load this file by absolute path and re-export the names.

The functions are pure (selection + partition) except ``_probe_reachable``,
which performs the one bounded reachability check per machine. The probe is
always INJECTED into ``_select_machines`` by the caller's tests as a fake, so no
live Docker/SSH ever runs under test.

Apportionment: the weighted split uses the largest-remainder (Hamilton) method
so the per-machine counts sum EXACTLY to the item count (Balinski & Young,
*Fair Representation*, 1982; the Hamilton/largest-remainder rule).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Probe budgets — bounded so a powered-off box never hangs the run.
_PROBE_DOCKER_TIMEOUT = 15
_PROBE_SSH_TIMEOUT = 10


class RemoteUnavailableError(RuntimeError):
    """A configured REMOTE quality machine (Dell) did not answer its probe.

    Fail-CLOSED policy: heavy quality work runs on the remote helper (Dell), not
    on the local Windows box. When a configured docker_context/ssh machine is
    unreachable we do NOT move its share onto Windows — we raise so the caller
    hard-fails with a clear "fix Dell" message. Windows only ever runs its own
    configured share, never a dead remote's.
    """


def _machines_from_config(cfg: dict) -> list[dict]:
    """Read the `machines` array, or synthesise the legacy two-machine list.

    Backward compatibility: a config with only the old
    `split{local_pct, remote_pct, remote_context}` block (no `machines` key)
    becomes [windows@local_pct, mint(context)@remote_pct] so today's mint-only
    setup keeps running as the same 65/35 two-way split.
    """
    machines = cfg.get("machines")
    if machines:
        return [dict(m) for m in machines]
    split = cfg.get("split", {})
    ctx = split.get("remote_context", "mint")
    return [
        {"name": "windows", "transport": "docker_local",
         "weight": split.get("local_pct", 0.65), "max_weight": 1.0},
        {"name": "mint", "transport": "docker_context", "context": ctx,
         "weight": split.get("remote_pct", 0.35), "max_weight": 1.0},
    ]


def _local_machine() -> dict:
    """The synthetic always-trusted local Windows machine (share 1.0).

    One definition shared by the all-off fallback in ``_select_machines`` and
    the gate's conservative local re-run of any failed remote slice (DRY).
    """
    return {"name": "windows", "transport": "docker_local",
            "weight": 1.0, "max_weight": 1.0, "share": 1.0}


def _renormalise_with_ceilings(machines: list[dict]) -> None:
    """Clamp each machine to its max_weight, then renormalise to sum 1.0.

    The ceiling is re-applied in a bounded loop so a cap (Dell 0.60) stays a
    ceiling after renormalisation pushes an uncapped machine's share up.
    Mutates each machine's `share` in place.
    """
    for m in machines:
        m["share"] = min(m["weight"], m.get("max_weight", 1.0))
    for _ in range(len(machines) + 1):
        total = sum(m["share"] for m in machines) or 1.0
        for m in machines:
            m["share"] = m["share"] / total
        over = [m for m in machines if m["share"] > m.get("max_weight", 1.0) + 1e-12]
        if not over:
            return
        free = sum(m["share"] for m in machines if m not in over) or 1.0
        budget = 1.0 - sum(m["max_weight"] for m in over)
        for m in machines:
            m["share"] = m["max_weight"] if m in over else m["share"] / free * budget


def _select_machines(cfg: dict, probe: Callable[[dict], bool] | None = None) -> list[dict]:
    """Keep reachable machines, apply ceilings, renormalise survivors to 1.0.

    `probe(machine) -> bool` is injected so unit tests pass a fake (no live
    Docker/SSH). Fail-CLOSED: a configured REMOTE machine (docker_context/ssh,
    i.e. Dell) that does not answer its probe raises ``RemoteUnavailableError``.
    Its share is NEVER redistributed onto the local Windows box — the caller
    must hard-fail and tell the operator to bring the remote (Dell) back. The
    local Windows machine still runs its OWN configured share when reachable.
    """
    if probe is None:
        probe = _probe_reachable
    machines = _machines_from_config(cfg)
    reachable_ids = {id(m) for m in machines if probe(m)}
    down_remotes = [
        m["name"] for m in machines
        if m["transport"] in ("docker_context", "ssh") and id(m) not in reachable_ids
    ]
    if down_remotes:
        raise RemoteUnavailableError(
            "Remote quality helper(s) unreachable: " + ", ".join(down_remotes)
            + ". Heavy quality runs on the remote (Dell), not on Windows. "
            "Wake or fix the remote and retry — Windows will NOT run it locally."
        )
    reachable = [m for m in machines if id(m) in reachable_ids]
    if not reachable:
        raise RemoteUnavailableError(
            "No quality machine is reachable (not even local Docker). "
            "Start Docker / fix the remote and retry."
        )
    _renormalise_with_ceilings(reachable)
    return reachable


def _probe_reachable(machine: dict) -> bool:
    """Bounded reachability check per transport; never raises, never hangs."""
    transport = machine["transport"]
    try:
        if transport == "docker_local":
            cmd = ["docker", "info", "--format", "{{.NCPU}}"]
            timeout = _PROBE_DOCKER_TIMEOUT
        elif transport == "docker_context":
            cmd = ["docker", "--context", machine["context"], "info"]
            timeout = _PROBE_DOCKER_TIMEOUT
        elif transport == "ssh":
            host = machine.get("ssh_host", machine["name"])
            cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, "true"]
            timeout = _PROBE_SSH_TIMEOUT
        else:
            return False
        
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout, cwd=str(REPO_ROOT),
            check=False,
        )
        rc = proc.returncode
        
        if rc != 0:
            print(f"PROBE FAILED for {machine['name']}: rc={rc} stdout={proc.stdout} stderr={proc.stderr}")

        if transport == "ssh":
            return rc != 255
        return rc == 0
    except Exception as e:
        print(f"PROBE EXCEPTION for {machine['name']}: {e}")
        return False


def _partition_weighted(items: list, machines: list[dict]) -> dict[str, list]:
    """Largest-remainder (Hamilton) split of items by each machine's `share`.

    Returns {machine name -> contiguous slice}. Counts sum EXACTLY to
    len(items): floors plus the leftover handed to the largest remainders,
    ties broken by input order so the result is deterministic.
    """
    n = len(items)
    floors, remainders = [], []
    for idx, m in enumerate(machines):
        raw = n * m["share"]
        floor = int(raw)
        floors.append(floor)
        remainders.append((raw - floor, idx))
    leftover = n - sum(floors)
    for _, idx in sorted(remainders, key=lambda r: (-r[0], r[1]))[:leftover]:
        floors[idx] += 1
    result: dict[str, list] = {}
    cursor = 0
    for count, m in zip(floors, machines):
        result[m["name"]] = items[cursor:cursor + count]
        cursor += count
    return result


def _dispatch_to_machines(
    machines: list[dict],
    plan: dict[str, list],
    per_machine: Callable[[dict, list], None],
) -> None:
    """Spawn one thread per machine that has a non-empty slice, then join all."""
    import threading

    threads: list[threading.Thread] = []
    for m in machines:
        slice_items = plan.get(m["name"]) or []
        if not slice_items:
            continue  # fail-open: empty slice → no thread, no container call
        t = threading.Thread(target=per_machine, args=(m, slice_items))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
