#!/usr/bin/env python3
"""Distribute the Django pytest suite across machines, Dell carrying ~88%.

Dell runs ~88% of the changed-test targets (config: ``pytest_machines`` in
``config/mutation-routing.json``); Windows runs the rest. Unlike lint, these
tests touch a database — so Dell runs them against ITS OWN empty Postgres +
Redis test stack (``docker-compose.dell-test.yml`` on the ``xf_dell_test_net``
network), never the live Windows database. The local slice runs against the
local test database exactly as today. The two stacks are independent, so the
two slices never share test state.

Reuses the proven building blocks rather than re-inventing them:

* the weighted split + fail-open machine selection come from the shared
  ``scripts/machine_routing.py`` (Hamilton largest-remainder, ceiling clamp);
* the Dell push is the SAME ``tar -> alpine extract -> sha256 manifest`` hand-
  shake the mutation, coverage, and lint gates use, into this gate's OWN named
  volume ``xf_test_repo`` so the gates never race on one volume.

Fail-open: if no Dell context answers the probe, the split collapses to a single
local machine and EVERY target runs locally (today's behaviour). If Dell answers
but its sync or manifest verify fails, that slice re-runs locally. Pass/fail is
unchanged — only WHERE each target runs.

Opt-in: callers set ``XF_PYTEST_SPLIT=1``. With it unset the existing single
local pytest run is used, so default behaviour does not change.

Concurrency safety: Dell runs its WHOLE slice in ONE pytest process against ONE
test database, so there is no within-Dell database contention. Dell's slice and
the local slice run concurrently but hit different databases on different
machines, so they cannot collide either.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Same tar exclude recipe the other sharders use — the Dell side re-hashes the
# SAME bytes, so the exclude list MUST match exactly or the manifest fails.
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _sync_tar_excludes import TAR_EXCLUDES as _TAR_EXCLUDES  # noqa: E402
_SYNC_ROOTS = (
    "backend",
    ".githooks",
    ".github",
    "config",
    "grafana",
    "scripts",
    "config.alloy",
    "loki-config.yaml",
    "otelcol-config.yaml",
    "pyroscope.yaml",
    "docker-compose.yml",
    "docker-compose.dell-test.yml",
    "pytest.ini",
)

# This gate's OWN source-snapshot volume on the remote, parallel to
# xf_mutation_repo / xf_coverage_repo / xf_lint_repo.
_TEST_VOLUME = "xf_test_repo"
_IMAGE = "xf-linker-backend-quality:latest"
_DELL_COMPILED_VOLUME = "xf_dell_compiled_repo"

# The network created by docker-compose.dell-test.yml; the test container joins
# it so the hostnames `postgres` and `redis` resolve to Dell's own test stack.
_DELL_TEST_NET = "xf_dell_test_net"

_LOCAL_ONLY_TARGET_PARTS = (
    "apps/observability/tests_faro_alloy_smoke.py",
    "apps/realtime/tests_sidecars_characterization.py",
)

# Pytest flags shared by both the Dell and local slices, mirroring the existing
# scoped run in scripts/run-python-quality.sh (random order, reuse the test DB
# so migrations run once). `--override-ini addopts=` drops the repo's heavy
# default addopts (coverage, etc.) so a scoped shard stays fast.
_PYTEST_FLAGS = ("--override-ini", "addopts=", "-p", "randomly", "-q", "--reuse-db", "-o", "cache_dir=/tmp/xf-test-cache/pytest")


def _configure_stdout() -> None:
    """Force UTF-8 output so Windows can print merged remote test output."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


def _load_machine_routing():
    """Import the shared machine-routing math by absolute path (single-sourced)."""
    path = REPO_ROOT / "scripts" / "machine_routing.py"
    spec = importlib.util.spec_from_file_location("machine_routing", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_pytest_routing_config() -> dict:
    """Read the ``pytest_machines`` block from config/mutation-routing.json.

    Falls back to a Dell-1.0 / Windows-0.0 pair (fail-closed: Dell does 100%,
    MSI 0%) if the key is absent.
    """
    path = REPO_ROOT / "config" / "mutation-routing.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    machines = cfg.get("pytest_machines")
    if not machines:
        machines = [
            {"name": "dell", "transport": "docker_context", "context": "dell",
             "weight": 1.0, "max_weight": 1.0},
            {"name": "windows", "transport": "docker_local",
             "weight": 0.0, "max_weight": 1.0},
        ]
    return {"machines": machines}


def _target_file(rel: str) -> str:
    """Return the backend-relative file path from a pytest target."""
    return rel.split("::", 1)[0]


def _target_files(rel_slice: list[str]) -> list[str]:
    """Return unique backend-relative files from pytest targets."""
    return list(dict.fromkeys(_target_file(rel) for rel in rel_slice))


def _host_hashes(rel_slice: list[str]) -> dict[str, str]:
    """sha256 of each backend/<rel> target the host ships to the remote."""
    hashes: dict[str, str] = {}
    for rel in _target_files(rel_slice):
        try:
            data = (REPO_ROOT / "backend" / rel).read_bytes()
        except OSError:
            continue
        hashes[rel] = hashlib.sha256(data).hexdigest()
    return hashes


def _tar_producer(env: dict) -> subprocess.Popen:
    """One tar producer (backend + .githooks, shared exclude list) for the push."""
    return subprocess.Popen(
        ["tar", "-cf", "-", *_TAR_EXCLUDES, *_SYNC_ROOTS],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )


def _sync_source_to_context(context: str, env: dict) -> str | None:
    """Push a FULL source snapshot into xf_test_repo on the remote context."""
    extractor = [
        "docker", "--context", context, "run", "--rm", "-i",
        "-v", f"{_TEST_VOLUME}:/repo",
        "alpine:latest", "sh", "-c",
        "tar -xf - -C /repo && mkdir -p /repo/audit && chmod 777 /repo/audit",
    ]
    try:
        tar = _tar_producer(env)
        sink = subprocess.Popen(
            extractor, stdin=tar.stdout, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", env=env,
        )
        tar.stdout.close()
        out, _ = sink.communicate(timeout=300)
        tar_rc = tar.wait()
    except FileNotFoundError:
        return f"{context} source sync failed: tar or docker not found on PATH."
    except subprocess.TimeoutExpired:
        return f"{context} source sync timed out after 5 minutes."
    if tar_rc != 0 or sink.returncode != 0:
        return f"{context} source sync failed:\n" + (out or "")
    return None


def _run_remote_sha(context: str, env: dict):
    """Return ``run_remote(rel_slice)->(rc,out)`` that sha256sums the remote copy."""
    def run_remote(rel_slice: list[str]) -> tuple[int, str]:
        cmd = [
            "docker", "--context", context, "run", "--rm",
            "-v", f"{_TEST_VOLUME}:/repo", "-w", "/repo/backend",
            "alpine:latest", "sh", "-c", "sha256sum " + " ".join(_target_files(rel_slice)),
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=REPO_ROOT, text=True, encoding="utf-8",
                errors="replace", capture_output=True, timeout=120, env=env,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 1, f"{context} manifest handshake could not run."
        return proc.returncode, proc.stdout + proc.stderr
    return run_remote


def _verify_snapshot(run_remote, rel_slice: list[str],
                     host_hashes: dict[str, str]) -> bool:
    """True only if the remote sha256 of every slice target matches the host's."""
    rc, out = run_remote(rel_slice)
    if rc != 0:
        return False
    remote: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            remote[parts[-1].replace("\\", "/")] = parts[0].strip()
    return all(remote.get(rel) == host_hashes.get(rel) for rel in _target_files(rel_slice))


def _remote_pytest_cmd(context: str, targets: list[str]) -> list[str]:
    """The ``docker --context <ctx> run`` command that runs a pytest slice on Dell.

    Joins Dell's test-stack network so `postgres`/`redis` resolve to Dell's own
    empty test database, passes the repo .env for required settings (SECRET_KEY
    etc.), then OVERRIDES only the DB/Redis hosts so the live machine is never
    touched.
    """
    return [
        "docker", "--context", context, "run", "--rm",
        "--network", _DELL_TEST_NET,
        "-v", f"{_TEST_VOLUME}:/repo",
        "-v", f"{_DELL_COMPILED_VOLUME}:/opt/xf/compiled",
        "-v", "xf_dell_quality_cache:/tmp/xf-test-cache",
        "-w", "/repo/backend",
        "--env-file", str(REPO_ROOT / ".env"),
        "-e", "DJANGO_SETTINGS_MODULE=config.settings.test",
        "-e", "POSTGRES_HOST=postgres",
        "-e", "REDIS_URL=redis://redis:6379/0",
        "-e", "CELERY_BROKER_URL=redis://redis:6379/2",
        "-e", "PYTHONPATH=/opt/xf/compiled/backend:/repo/backend",
        _IMAGE,
        "python", "-m", "pytest", *_PYTEST_FLAGS, *targets,
    ]


def _local_pytest_cmd(targets: list[str]) -> list[str]:
    """The ``docker compose run`` command that runs a pytest slice locally."""
    return [
        "docker", "compose", "run", "--rm", "-T", "-w", "/repo/backend",
        "backend-quality", "python", "-m", "pytest", *_PYTEST_FLAGS, *targets,
    ]


def _run(cmd: list[str], env: dict, timeout: int) -> tuple[int, str]:
    """Run a command, never raise; return (rc, combined-output)."""
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=timeout, env=env, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, f"pytest command could not run: {exc}"
    return proc.returncode, proc.stdout + proc.stderr


def _pytest_slice_on_remote(context: str, targets: list[str]) -> tuple[int, str] | None:
    """Sync source once, verify it, then run the whole pytest slice on the remote.

    Returns (rc, output), or None when the slice could not be trusted (sync or
    manifest verify failed) so the caller re-runs it locally.
    """
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    if _sync_source_to_context(context, env) is not None:
        return None
    if not _verify_snapshot(_run_remote_sha(context, env), targets, _host_hashes(targets)):
        return None
    # Fix permission for xf_dell_quality_cache before pytest runs as non-root user
    subprocess.run(["docker", "--context", context, "run", "--rm", "-v", "xf_dell_quality_cache:/tmp/xf-test-cache", "alpine:latest", "chmod", "-R", "777", "/tmp/xf-test-cache"], env=env, check=False)
    return _run(_remote_pytest_cmd(context, targets), env, timeout=1800)


def _pytest_slice_local(targets: list[str]) -> tuple[int, str]:
    """Run one pytest slice on the always-trusted local Windows backend-quality."""
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    return _run(_local_pytest_cmd(targets), env, timeout=1800)


def _is_local_only_target(target: str) -> bool:
    """True when a test talks to services only running on the Windows stack."""
    target_file = _target_file(target).replace("\\", "/")
    return any(part in target_file for part in _LOCAL_ONLY_TARGET_PARTS)


def _split_local_only_targets(targets: list[str]) -> tuple[list[str], list[str]]:
    """Return (shardable, local_only) while preserving target order."""
    shardable: list[str] = []
    local_only: list[str] = []
    for target in targets:
        if _is_local_only_target(target):
            local_only.append(target)
        else:
            shardable.append(target)
    return shardable, local_only


def run_pytest_sharded(targets: list[str]) -> tuple[int, str]:
    """Split test targets across machines, run each slice, merge into one verdict.

    Overall rc is the max over slices (any non-zero = failure). Output is
    concatenated with a per-machine header so a failure is traceable to the
    machine that found it.
    """
    if not targets:
        return 0, "[PYTEST SPLIT: no changed test targets]\n"
    routing = _load_machine_routing()
    machines = routing._select_machines(_load_pytest_routing_config())
    shardable_targets, local_only_targets = _split_local_only_targets(targets)
    plan = routing._partition_weighted(shardable_targets, machines)
    if local_only_targets:
        local_machine = next(
            (machine for machine in machines if machine["transport"] != "docker_context"),
            machines[0],
        )
        plan.setdefault(local_machine["name"], []).extend(local_only_targets)

    results: dict[str, tuple[int, str]] = {}
    lock = threading.Lock()

    def per_machine(machine: dict, slice_targets: list[str]) -> None:
        if machine["transport"] == "docker_context":
            outcome = _pytest_slice_on_remote(machine.get("context", "dell"), slice_targets)
            where = machine["name"]
            if outcome is None:  # untrusted → fail-open re-run locally
                outcome = _pytest_slice_local(slice_targets)
                where = f"{machine['name']}->local(unverified)"
        else:
            outcome = _pytest_slice_local(slice_targets)
            where = f"{machine['name']}(local)"
        with lock:
            results[machine["name"]] = outcome
            sys.stdout.write(
                f"[PYTEST SPLIT: {where} -> {len(slice_targets)} target(s)]\n"
            )

    routing._dispatch_to_machines(machines, plan, per_machine)

    rc = max((r[0] for r in results.values()), default=0)
    body = "".join(
        f"----- pytest @ {name} (rc={r[0]}) -----\n{r[1]}"
        for name, r in sorted(results.items())
        if r[1].strip()
    )
    return rc, body


def _append_evidence(evidence_out, **fields) -> None:
    """Append one QualityEvidence JSON-lines row via the shared writer.

    Loaded by absolute path (same pattern as machine_routing) so the row shape
    is IDENTICAL to what the in-container pytest step writes.
    """
    path = REPO_ROOT / "scripts" / "write_quality_evidence.py"
    spec = importlib.util.spec_from_file_location("write_quality_evidence", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.append_evidence_row(evidence_out, **fields)


def _write_pytest_evidence(evidence_out, rc: int) -> None:
    """Record the sharded pytest run's merged verdict as one QualityEvidence row."""
    passed = rc == 0
    _append_evidence(
        evidence_out, check_type="normal_test",
        status="passed" if passed else "failed", tool_name="pytest",
        command="run_pytest_on_context.py --targets <changed test targets> (sharded Dell 88%)",
        summary=f"Sharded backend pytest targets {'passed' if passed else 'failed'}.",
        failure_fingerprint=f"pytest:{rc}",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--targets", nargs="*", default=[],
        help="backend-relative pytest targets (e.g. apps/foo/tests.py).",
    )
    parser.add_argument(
        "--evidence-out", default=None,
        help="JSON-lines path; when set, append one QualityEvidence row for pytest.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv if argv is not None else sys.argv[1:]))
    targets = [t.replace("\\", "/").removeprefix("backend/") for t in args.targets if t.strip()]
    evidence_out = Path(args.evidence_out) if args.evidence_out else None
    if not targets:
        sys.stdout.write("[PYTEST SPLIT: no changed test targets — nothing to run]\n")
        return 0
    rc, out = run_pytest_sharded(targets)
    if out:
        sys.stdout.write(out)
    sys.stdout.write(f"[PYTEST RESULT: rc={rc}]\n")
    if evidence_out is not None:
        _write_pytest_evidence(evidence_out, rc)
    return rc


if __name__ == "__main__":
    _configure_stdout()
    raise SystemExit(main())
