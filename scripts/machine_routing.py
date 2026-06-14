#!/usr/bin/env python3
"""Shared machine-routing math for weighted N-way quality work.

This tiny module is the SINGLE SOURCE of the machine-selection and
weighted-partition logic used by the quality runners:

* ``scripts/turbo_mutation.py`` — the per-language mutation sweep.
* ``scripts/run_pytest_on_context.py`` — the sharded pytest path.
* ``scripts/run_lint_on_context.py`` — the sharded lint/type-check path.
* ``scripts/turbo_tests.py`` — the split test runner.

It has ZERO Django imports and does NOT import any caller. Every caller
importlib-loads this file by absolute path and re-exports the names.

The functions are pure (selection + partition) except ``_probe_reachable``,
which performs the one bounded reachability check per machine. The probe is
always INJECTED into ``_select_machines`` by the caller's tests as a fake, so no
live Docker/SSH ever runs under test.

Apportionment: the weighted split uses the largest-remainder (Hamilton) method
so the per-machine counts sum EXACTLY to the item count (Balinski & Young,
*Fair Representation*, 1982; the Hamilton/largest-remainder rule).
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Probe budgets — bounded so a powered-off box never hangs the run.
_PROBE_DOCKER_TIMEOUT = 15
_PROBE_SSH_TIMEOUT = 10

# Docker context names that mean "the local Docker Desktop engine". On the
# Windows host (the MSI) these are forbidden quality targets — tests, lint,
# coverage, and mutation run on the Dell helper only.
_LOCAL_CONTEXT_NAMES = frozenset({"", "default", "desktop-linux", "desktop-windows"})


def _on_windows_host() -> bool:
    """True on the bare Windows host (the MSI); CI runners are exempt."""
    if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true":
        return False
    return platform.system() == "Windows"


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


def _assert_no_local_context_on_windows(machines: list[dict]) -> None:
    """On the MSI, forbid any docker_context that points at the local engine."""
    if not _on_windows_host():
        return
    local_targets = [
        m["name"] for m in machines
        if m["transport"] == "docker_context"
        and m.get("context", "") in _LOCAL_CONTEXT_NAMES
    ]
    if local_targets:
        raise RemoteUnavailableError(
            "Machine(s) " + ", ".join(local_targets)
            + " point at the local Docker Desktop engine. Tests and "
            "mutation runs are blocked on this Windows machine (MSI) — "
            "route the work to the Dell docker context instead."
        )


def _select_machines(
    cfg: dict,
    probe: Callable[[dict], bool] | None = None,
    readiness_probe: Callable[[dict], bool] | None = None,
) -> list[dict]:
    """Keep usable machines, apply ceilings, renormalise survivors to 1.0.

    `probe(machine) -> bool` is injected so unit tests pass a fake (no live
    Docker/SSH). Fail-CLOSED for REQUIRED remotes: a configured docker_context/
    ssh machine (i.e. Dell, the authority) that does not answer its probe raises
    ``RemoteUnavailableError`` — its share is NEVER moved onto Windows.

    OPTIONAL overflow machines (``optional: true``, e.g. an idle Mint) are the
    exception: when they are down, busy, or missing their image they are simply
    DROPPED and the authority machine renormalises to carry the work — they
    never fail the run. A machine flagged ``idle_only``/``requires_image`` must
    also pass ``readiness_probe`` (idle enough + image present) to participate.
    """
    if probe is None:
        probe = _probe_reachable
    if readiness_probe is None:
        readiness_probe = _probe_ready
    machines = _machines_from_config(cfg)
    _assert_no_local_context_on_windows(machines)
    reachable_ids = {id(m) for m in machines if probe(m)}
    # Optional overflow machines must ALSO be ready (idle + image present); a
    # reachable-but-not-ready overflow box is dropped here, never fatal below.
    for m in machines:
        if id(m) in reachable_ids and (m.get("idle_only") or m.get("requires_image")):
            if not readiness_probe(m):
                reachable_ids.discard(id(m))
    down_remotes = [
        m["name"] for m in machines
        if m["transport"] in ("docker_context", "ssh")
        and not m.get("optional", False)
        and id(m) not in reachable_ids
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


def _remote_image_present(ctx: str, image: str) -> bool:
    """True only if `image` already exists on the `ctx` docker engine."""
    try:
        proc = subprocess.run(
            ["docker", "--context", ctx, "image", "inspect", image],
            capture_output=True, timeout=_PROBE_DOCKER_TIMEOUT,
            cwd=str(REPO_ROOT), check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _remote_is_idle(ctx: str, load_per_core: float) -> bool:
    """True only if the `ctx` host's 1-min load is at or below idle threshold.

    Reads the host load average and core count via a tiny alpine container
    (load average is not namespaced, so the container sees the real host load).
    Any error returns False — an uncertain box is treated as busy.
    """
    try:
        proc = subprocess.run(
            ["docker", "--context", ctx, "run", "--rm", "alpine",
             "sh", "-c", "cat /proc/loadavg && nproc"],
            capture_output=True, timeout=_PROBE_DOCKER_TIMEOUT,
            cwd=str(REPO_ROOT), text=True, check=False,
        )
        if proc.returncode != 0:
            return False
        tokens = proc.stdout.split()
        load1 = float(tokens[0])
        cores = int(tokens[-1])
        return cores > 0 and load1 <= cores * load_per_core
    except Exception:
        return False


def _probe_ready(machine: dict) -> bool:
    """Is an OPTIONAL overflow machine ready to take a share right now?

    Conservative, both checks via the machine's docker context:
      * ``requires_image`` (if set) — that image must already be present, so an
        overflow box never tries to run a tool it has not got.
      * ``idle_only`` (if set) — the host's 1-min load must be <=
        ``idle_load_per_core`` (default 0.5) x cores, so we only borrow a
        genuinely idle helper (e.g. Mint while it is just running the k3s
        control plane). Any uncertainty -> not ready, so we never pile work on it.
    """
    if machine.get("transport") != "docker_context":
        return True
    ctx = machine.get("context", "")
    image = machine.get("requires_image")
    if image and not _remote_image_present(ctx, image):
        return False
    if machine.get("idle_only") and not _remote_is_idle(
        ctx, machine.get("idle_load_per_core", 0.5)
    ):
        return False
    return True


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
