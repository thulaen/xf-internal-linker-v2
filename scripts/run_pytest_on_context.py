#!/usr/bin/env python3
"""Run the Django pytest suite on the Dell docker context — Dell-only, fail-closed.

Dell runs 100% of the changed-test targets (config: ``pytest_machines`` in
``config/mutation-routing.json``). Unlike lint, these tests touch a database —
so Dell runs them against ITS OWN empty Postgres + Redis test stack
(``docker-compose.dell-test.yml`` on the ``xf_dell_test_net`` network), never
the live Windows database. There is NO local execution path: every selected
machine must use the ``docker_context`` transport, and a slice routed to any
other transport fails the run.

Reuses the proven building blocks rather than re-inventing them:

* the weighted split + machine selection come from the shared
  ``scripts/machine_routing.py`` (Hamilton largest-remainder, ceiling clamp);
* the Dell push is the SAME ``tar -> alpine extract -> sha256 manifest`` hand-
  shake the mutation, coverage, and lint gates use, into this gate's OWN named
  volume ``xf_test_repo`` so the gates never race on one volume.

Fail-CLOSED end to end: if the configured Dell context does not answer its
reachability probe, ``machine_routing._select_machines`` raises and this gate
hard-fails with a "fix Dell" message — work is NEVER silently moved to another
machine. If Dell answers the probe but a slice's source sync or sha256 manifest
verify fails mid-run, that slice FAILS (rc=1) instead of running anywhere else.
Tests that need services absent from Dell's bare test stack must self-skip
(see ``backend/apps/observability/tests_faro_alloy_smoke.py``).

For LOCAL commits ``scripts/run-python-quality.sh`` defaults ``XF_PYTEST_SPLIT=1``
so Dell runs 100% of the changed test targets; CI keeps it off and runs them in
the CI container.

Coverage visibility: pass ``--cov-targets apps.foo,apps.bar`` (comma-separated
or repeated) to add ``--cov=<target>`` flags plus ``--cov-report=term`` to the
remote pytest command, so coverage shows up in the merged Dell output.

Concurrency safety: Dell runs its WHOLE slice in ONE pytest process against ONE
test database, so there is no within-Dell database contention.
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
# The exact repo roots tarred to Dell for every pytest run. This tuple IS the
# tar command's file list — edit here to change what reaches /repo on Dell.
_SYNC_ROOTS = (
    "backend",
    "rust",
    "services",
    ".gitattributes",
    ".githooks",
    "docs",
    "config",
    "docker-compose.yml",
    ".env.example",
    "nginx",
    "otelcol-config.yaml",
    "frontend/src/app",
    "scripts",
)

# This gate's OWN source-snapshot volume on the remote, parallel to
# xf_mutation_repo / xf_coverage_repo / xf_lint_repo.
_TEST_VOLUME = "xf_test_repo"
_IMAGE = "xf-linker-backend-quality:latest"
_DELL_COMPILED_VOLUME = "xf_dell_compiled_repo"

# The network created by docker-compose.dell-test.yml; the test container joins
# it so the hostnames `postgres` and `redis` resolve to Dell's own test stack.
_DELL_TEST_NET = "xf_dell_test_net"

# Pytest flags for the Dell slices, mirroring the existing scoped run in
# scripts/run-python-quality.sh (random order, reuse the test DB so migrations
# run once). `--override-ini addopts=` drops the repo's heavy default addopts
# (coverage, etc.) so a scoped shard stays fast.
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

    Falls back to Dell at weight 1.0 (fail-closed: Dell does 100%, nothing runs
    on the local machine) if the key is absent.
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
        print("REMOTE SHA FAILED. rc=", rc, "out=", out)
        return False
    remote: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            remote[parts[-1].replace("\\", "/")] = parts[0].strip()
    match = all(remote.get(rel) == host_hashes.get(rel) for rel in _target_files(rel_slice))
    if not match:
        print("HOST HASHES:", host_hashes)
        print("REMOTE HASHES:", remote)
    return match


def _remote_pytest_cmd(context: str, targets: list[str],
                       cov_targets: list[str] | None = None) -> list[str]:
    """The ``docker --context <ctx> run`` command that runs a pytest slice on Dell.

    Joins Dell's test-stack network so `postgres`/`redis` resolve to Dell's own
    empty test database, passes the repo .env for required settings (SECRET_KEY
    etc.), then OVERRIDES only the DB/Redis hosts so the live machine is never
    touched. When ``cov_targets`` is given, one ``--cov=<target>`` flag per
    entry plus ``--cov-report=term`` keep coverage visible in the merged output.
    """
    cov_flags: list[str] = []
    if cov_targets:
        cov_flags = [f"--cov={t}" for t in cov_targets] + ["--cov-report=term"]
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
        "-e", "PYTHONPATH=/opt/xf/compiled/active:/opt/xf/compiled:/repo/backend",
        _IMAGE,
        "python", "-m", "pytest", *_PYTEST_FLAGS, *cov_flags, *targets,
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


def _pytest_slice_on_remote(context: str, targets: list[str],
                            cov_targets: list[str] | None = None) -> tuple[int, str] | None:
    """Sync source once, verify it, then run the whole pytest slice on the remote.

    Returns (rc, output), or None when the slice could not be trusted (sync or
    manifest verify failed) so the caller fails the run (fail-closed).
    """
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    if (sync_err := _sync_source_to_context(context, env)) is not None:
        print("SYNC ERR:", sync_err)
        return None
    if not _verify_snapshot(_run_remote_sha(context, env), targets, _host_hashes(targets)):
        print("VERIFY ERR: snapshot mismatch!")
        return None
    # Fix permission for xf_dell_quality_cache before pytest runs as non-root user
    subprocess.run(["docker", "--context", context, "run", "--rm", "-v", "xf_dell_quality_cache:/tmp/xf-test-cache", "alpine:latest", "chmod", "-R", "777", "/tmp/xf-test-cache"], env=env, check=False)
    return _run(_remote_pytest_cmd(context, targets, cov_targets), env, timeout=1800)


def run_pytest_sharded(targets: list[str],
                       cov_targets: list[str] | None = None) -> tuple[int, str]:
    """Split test targets across machines, run each slice, merge into one verdict.

    Overall rc is the max over slices (any non-zero = failure). Output is
    concatenated with a per-machine header so a failure is traceable to the
    machine that found it.
    """
    if not targets:
        return 0, "[PYTEST SPLIT: no changed test targets]\n"
    routing = _load_machine_routing()
    machines = routing._select_machines(_load_pytest_routing_config())
    plan = routing._partition_weighted(targets, machines)

    results: dict[str, tuple[int, str]] = {}
    lock = threading.Lock()

    def per_machine(machine: dict, slice_targets: list[str]) -> None:
        if machine["transport"] != "docker_context":
            with lock:
                results[machine["name"]] = (1, "transport not allowed; pytest runs only on the Dell docker context")
            return
        outcome = _pytest_slice_on_remote(
            machine.get("context", "dell"), slice_targets, cov_targets
        )
        where = machine["name"]
        if outcome is None:  # untrusted -> fail-closed
            outcome = (1, f"Dell source sync or manifest verification failed for pytest.")
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
    # rc=5 means no tests collected, which is a success for scoped runs.
    passed = rc == 0 or rc == 5
    _append_evidence(
        evidence_out, check_type="normal_test",
        status="passed" if passed else "failed", tool_name="pytest",
        command="run_pytest_on_context.py --targets <changed test targets> (sharded Dell 100%)",
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
    parser.add_argument(
        "--cov-targets", action="append", default=[],
        help="coverage targets (e.g. apps.foo); comma-separated or repeated. "
             "Each adds --cov=<target> plus --cov-report=term to the remote run.",
    )
    parser.add_argument(
        "--cache-map", default=None,
        help="JSON file mapping {test target: [source files]} (the selector's "
             "--map-out). Cache keys then include the source contents, so a "
             "changed source re-runs its tests even when the test file itself "
             "is unchanged.",
    )
    return parser.parse_args(argv)


def _load_cache_map(path_text: str | None) -> dict[str, list[str]]:
    """Read the selector's target-to-sources map; a bad map means no map."""
    if not path_text:
        return {}
    try:
        loaded = json.loads(Path(path_text).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(key): [str(item) for item in values]
            for key, values in loaded.items() if isinstance(values, list)}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv if argv is not None else sys.argv[1:]))
    targets = [t.replace("\\", "/").removeprefix("backend/") for t in args.targets if t.strip()]
    cov_targets = [
        part.strip()
        for chunk in args.cov_targets
        for part in chunk.split(",")
        if part.strip()
    ]
    evidence_out = Path(args.evidence_out) if args.evidence_out else None
    
    if not targets:
        sys.stdout.write("[PYTEST SPLIT: no changed test targets — nothing to run]\n")
        return 0

    from quality_cache import QualityCache
    cache = QualityCache(REPO_ROOT)
    cache_map = _load_cache_map(args.cache_map)
    subjects = {
        t: cache.subject_hash_for_files(
            [REPO_ROOT / "backend" / _target_file(t)]
            + [REPO_ROOT / "backend" / src for src in cache_map.get(t, [])]
        )
        for t in targets
    }
    to_run, skipped = cache.filter("pytest", subjects)
    
    if skipped:
        sys.stdout.write(f"[PYTEST CACHE: skipped {len(skipped)} unchanged targets]\n")
    if not to_run:
        sys.stdout.write("[PYTEST CACHE: all targets unchanged — nothing to run]\n")
        if evidence_out is not None:
            _write_pytest_evidence(evidence_out, 0)
        return 0

    rc, out = run_pytest_sharded(to_run, cov_targets=cov_targets)
    if out:
        sys.stdout.write(out)
    
    sys.stdout.write(f"[PYTEST RESULT: rc={rc}]\n")
    if evidence_out is not None:
        _write_pytest_evidence(evidence_out, rc)
    
    if rc == 0 or rc == 5:
        cache.record("pytest", [subjects[t] for t in to_run])
    
    # Return 0 if rc is 5 (no tests collected) to prevent shell script failures.
    return 0 if rc == 5 else rc


if __name__ == "__main__":
    _configure_stdout()
    raise SystemExit(main())
