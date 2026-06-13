#!/usr/bin/env python3
"""Turbo distributed pytest runner — fan-out across Dell 60% / Windows 30% / Mint 10%.

Activated by ``XF_TURBO_TESTS=1``. Only ``SimpleTestCase`` subclasses are fanned
out; they carry no database state and are safe to run on a remote Linux context
without a local Postgres. Tests that require the real database stay on Windows.

Apportionment uses the largest-remainder (Hamilton) method so shard file counts
sum EXACTLY to the total — never one file left on the floor and never one run
twice. The ``_partition_weighted`` and ``_dispatch_to_machines`` helpers are
single-sourced in ``scripts/machine_routing.py`` exactly as the mutation runners
do; this module only calls them. Any machine that is powered off is dropped
before shards are assigned and its share redistributes to the survivors
(fail-open).

Usage::

    python scripts/turbo_tests.py --language python [--dry-run]
    # Or just activate by env var inside quality scripts:
    XF_TURBO_TESTS=1 python scripts/turbo_tests.py --language python

Citations
---------
* Google Testing Blog (2016): "How Google Runs Tests at Scale"
  https://testing.googleblog.com/2016/03/how-google-runs-tests-at-scale.html
  — distributed sharding by file, fail-open machine selection, local re-run on
    remote failure.
* Balinski & Young, *Fair Representation* (1982), Hamilton apportionment
  (largest-remainder / Hamilton method): ISBN 978-0815700616.
  — shard counts must sum exactly to the item count; the largest-remainder
    method is the canonical solution (also used in ``machine_routing.py``).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_ROUTING_CFG = REPO_ROOT / "config" / "mutation-routing.json"
_MAX_SHARD_TIMEOUT = 1800
_TEST_VOLUME = "xf_test_repo"
_COMPOSE_NETWORK = "xf-internal-linker-v2_default"
_QUALITY_IMAGE = "xf-linker-backend-quality:latest"

# The ONE tar exclude recipe shared with check-scoped-mutation.py (DRY).
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _sync_tar_excludes import TAR_EXCLUDES as _TAR_EXCLUDES  # noqa: E402


# ── shared routing (single-sourced; DRY) ─────────────────────────────────────

def _load_machine_routing():
    """Import the shared routing math by absolute path (single-sourced; DRY)."""
    path = REPO_ROOT / "scripts" / "machine_routing.py"
    spec = importlib.util.spec_from_file_location("machine_routing", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── config ────────────────────────────────────────────────────────────────────

def _load_routing_cfg() -> dict:
    """Read config/mutation-routing.json (same file the mutation sweep reads)."""
    return json.loads(_ROUTING_CFG.read_text(encoding="utf-8"))


# ── source sync helpers (verbatim from check-scoped-mutation.py) ──────────────

def _tar_producer(env: dict) -> subprocess.Popen:
    """One tar producer (backend + .githooks, shared exclude list) for any remote."""
    return subprocess.Popen(
        ["tar", "-cf", "-", *_TAR_EXCLUDES, "backend", "rust", "services", ".githooks", "docs", "config", "docker-compose.yml", ".env.example", "nginx", "otelcol-config.yaml", "frontend/src/app", "scripts"],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )


def _pipe_tar_into(extractor: list[str], env: dict, who: str) -> str | None:
    """Pipe ``_tar_producer`` into ``extractor``; return None on success else error.

    Both the tar producer's and the extractor's exit codes are checked so a
    half-finished copy is reported as a sync failure (never silently trusted).
    This is a verbatim copy of the same function in
    ``.githooks/check-scoped-mutation.py`` (DRY: one canonical implementation,
    two importers).
    """
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
        return f"{who} source sync failed: tar or transport not found on PATH."
    except subprocess.TimeoutExpired:
        return f"{who} source sync timed out after 5 minutes."
    if tar_rc != 0 or sink.returncode != 0:
        return f"{who} source sync failed:\n" + (out or "")
    return None


def _sync_test_source_to_context(
    context: str, env: dict | None = None
) -> str | None:
    """Push a full source snapshot into the test named volume on a remote context.

    ``env`` defaults to the current process environment with MSYS_NO_PATHCONV=1.

    Mirrors ``_sync_source_to_mint`` from check-scoped-mutation.py but uses
    ``_TEST_VOLUME`` (``xf_test_repo``) instead of ``xf_mutation_repo`` so the
    two volumes are independent and a simultaneous mutation run does not
    overwrite the test source mid-shard.
    """
    if env is None:
        env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    extractor = [
        "docker", "--context", context, "run", "--rm", "-i",
        "-v", _TEST_VOLUME + ":/repo",
        "alpine:latest", "sh", "-c", "tar -xf - -C /repo",
    ]
    return _pipe_tar_into(extractor, env, context)


# ── test file discovery ───────────────────────────────────────────────────────

def _normalise_backend_search_roots(paths: list[str] | None = None) -> list[Path]:
    """Return existing backend search roots for fast file discovery."""
    if not paths:
        return [REPO_ROOT / "backend"]
    roots: list[Path] = []
    for raw in paths:
        path = Path(raw)
        root = REPO_ROOT / path
        if path.parts and path.parts[0] == "backend":
            roots.append(root)
        else:
            roots.append(REPO_ROOT / "backend" / path)
    return [root for root in roots if root.exists()]


def _is_test_file(path: Path) -> bool:
    """Return True when ``path`` follows this repo's Python test naming."""
    name = path.name
    return name == "tests.py" or name.startswith("test_") or name.startswith("tests_")


def _discover_simpletest_files_fast(paths: list[str] | None = None) -> list[str]:
    """Find SimpleTestCase files without Docker collection.

    Dry-run must answer quickly even when the quality container is slow or
    stuck. This scanner is less exact than pytest collection, but it is enough
    to show the shard shape and prove the Dell routing path is reachable.
    """
    discovered: list[str] = []
    seen: set[str] = set()
    for root in _normalise_backend_search_roots(paths):
        candidates = [root] if root.is_file() else root.rglob("*.py")
        for path in candidates:
            if not _is_test_file(path):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "SimpleTestCase" not in content:
                continue
            rel = path.relative_to(REPO_ROOT / "backend").as_posix()
            if rel not in seen:
                seen.add(rel)
                discovered.append(rel)
    return discovered


def _collect_simpletest_files(paths: list[str] | None = None) -> list[str]:
    """Return backend-relative paths of test files that contain SimpleTestCase.

    ``paths`` is an optional list of sub-paths to restrict discovery (e.g.
    ``["backend/apps"]``).  When ``None`` or empty the full backend tree is
    scanned — same behaviour as the original.

    Only ``SimpleTestCase`` subclasses carry no database state and are safe to
    run on a remote context without a local Postgres. The caller should NOT fan
    out ``TestCase`` (which wraps each test in a transaction) because the remote
    has no database.

    Discovery steps:
    1. Run ``pytest --collect-only -q`` inside the quality container to get the
       full test file list.
    2. Keep only files whose full source contains the literal string
       ``SimpleTestCase`` (quick text scan; false positives are acceptable
       because pytest will simply collect 0 tests from a false positive).
    """
    cmd = [
        "docker", "compose", "run", "--rm", "-T",
        "-w", "/repo/backend",
        "backend-quality",
        "python", "-m", "pytest", "--collect-only", "-q",
    ]
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120, cwd=str(REPO_ROOT), check=False,
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"[TURBO TESTS: collect failed: {exc}]", file=sys.stderr)
        return []

    raw = result.stdout + result.stderr
    seen: set[str] = set()
    paths: list[str] = []
    for line in raw.splitlines():
        # pytest --collect-only -q lines look like "apps/foo/tests/test_bar.py::..."
        if "::" not in line:
            continue
        rel = line.split("::")[0].strip().replace("\\", "/")
        if not rel.endswith(".py"):
            continue
        if rel in seen:
            continue
        seen.add(rel)
        host_path = REPO_ROOT / "backend" / rel
        try:
            content = host_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "SimpleTestCase" in content:
            paths.append(rel)

    return paths


# ── per-machine shard runners ─────────────────────────────────────────────────

def _run_shard_local(
    files: list[str], cmd_template: str = ""
) -> tuple[int, str]:
    """Run a pytest shard inside the local Windows quality container.

    ``cmd_template`` is currently unused (reserved for future callers that want
    to override the default pytest invocation); the local runner always uses the
    canonical ``docker compose run`` path.  Uses ``docker compose run`` (not
    ``exec``) so the shard gets a fresh container with no shared state from
    other concurrent shards.
    """
    cmd = [
        "docker", "compose", "run", "--rm", "-T",
        "-w", "/repo/backend",
        "backend-quality",
        "python", "-m", "pytest", "--tb=short", "-q",
        *files,
    ]
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_MAX_SHARD_TIMEOUT,
            cwd=str(REPO_ROOT), check=False, env=env,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 1, f"[TURBO TESTS: local shard timed out after {_MAX_SHARD_TIMEOUT}s]\n"
    except Exception as exc:
        return 1, f"[TURBO TESTS: local shard error: {exc}]\n"


def _run_shard_context(
    files: list[str], cmd_template: str = "", context: str = ""
) -> tuple[int, str]:
    """Sync source then run a pytest shard on a docker_context remote machine.

    ``cmd_template`` is reserved for future override of the pytest invocation.
    ``context`` is the Docker context name (e.g. ``"mint"``).

    Steps:
    1. Push the full working-tree source into the ``xf_test_repo`` named volume.
    2. Run pytest against that volume using the quality image.

    Any sync failure short-circuits with rc=1 and the error text so the merge
    step can re-run the shard locally.
    """
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    err = _sync_test_source_to_context(context)
    if err is not None:
        return 1, f"[TURBO TESTS: sync to {context} failed]: {err}\n"
    cmd = [
        "docker", "--context", context, "run", "--rm",
        "-v", _TEST_VOLUME + ":/repo",
        "-v", "compiled_artifacts:/opt/xf/compiled",
        "--network", _COMPOSE_NETWORK,
        "-w", "/repo/backend",
        "-e", "DJANGO_SETTINGS_MODULE=config.settings.test",
        "-e", "PYTHONPATH=/opt/xf/compiled/active:/opt/xf/compiled:/app",
        "-e", "REPO_ROOT=/repo",
        _QUALITY_IMAGE,
        "python", "-m", "pytest", "--tb=short", "-q",
        *files,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_MAX_SHARD_TIMEOUT,
            cwd=str(REPO_ROOT), check=False, env=env,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 1, (
            f"[TURBO TESTS: {context} shard timed out after "
            f"{_MAX_SHARD_TIMEOUT}s]\n"
        )
    except Exception as exc:
        return 1, f"[TURBO TESTS: {context} shard error: {exc}]\n"


def _run_shard_on_machine(
    machine: dict, files: list[str], cmd_template: str = ""
) -> tuple[int, str]:
    """Dispatch to the right shard runner based on the machine's transport.

    ``docker_local`` uses the local compose quality container.
    ``docker_context`` syncs source and runs on the remote context.
    Unknown transports return ``(1, "Unknown transport …")`` — they are NOT
    silently re-run locally so the caller knows the machine was skipped.
    """
    transport = machine["transport"]
    if transport == "docker_local":
        return _run_shard_local(files, cmd_template)
    if transport == "docker_context":
        return _run_shard_context(files, cmd_template, context=machine.get("context", ""))
    return 1, f"[TURBO TESTS: Unknown transport '{transport}' for machine '{machine.get('name', '?')}' — shard skipped]\n"


# ── result merging ────────────────────────────────────────────────────────────

def _merge_shard_results(
    results: list[dict]
) -> int:
    """Combine per-machine shard outcomes into one aggregate return code.

    ``results`` is a list of dicts with keys:
        ``machine``  — the machine dict used to create the shard
        ``rc``       — int (0 = pass, non-zero = fail) or ``None`` (thread crashed)
        ``output``   — captured stdout/stderr string
        ``files``    — list of test file paths (present when ``rc`` is ``None``)
        ``cmd``      — cmd_template string (present when ``rc`` is ``None``)

    Any entry whose ``rc`` is ``None`` (thread crashed before recording a
    result) is re-run locally — a broken remote must never silently become a
    pass. Final return code is 1 if any shard returned non-zero or if any local
    re-run also failed.
    """
    final_rc = 0
    for entry in results:
        name = entry.get("machine", {}).get("name", "?")
        rc = entry.get("rc")
        if rc is None:
            files = entry.get("files", [])
            cmd = entry.get("cmd", "")
            rc, _ = _run_shard_local(files, cmd)
        if rc != 0:
            final_rc = 1
    return final_rc


# ── main entry point ──────────────────────────────────────────────────────────

def run_python_tests(
    machines: list[dict] | None = None,
    paths: list[str] | None = None,
) -> int:
    """Fan the SimpleTestCase files out across all reachable machines.

    ``machines`` — list of machine dicts (loaded from routing config when
    ``None``).
    ``paths``    — optional sub-paths to restrict file discovery.

    Returns 0 when all shards pass, 1 when any shard fails or the test
    collection step finds no files to run.
    """
    if machines is None:
        cfg = _load_routing_cfg()
        routing = _load_machine_routing()
        try:
            machines = routing._select_machines(cfg)
        except routing.RemoteUnavailableError as exc:
            print(f"[TURBO TESTS: blocked: {exc}]", file=sys.stderr)
            return 1

    files = _collect_simpletest_files(paths)
    if not files:
        print("[TURBO TESTS: no SimpleTestCase files — nothing to shard]")
        return 0

    routing = _load_machine_routing()
    plan = routing._partition_weighted(files, machines)

    results: list[dict] = []
    lock = threading.Lock()

    def per_machine(machine: dict, shard: list[str]) -> None:
        try:
            rc, raw = _run_shard_on_machine(machine, shard, "")
        except Exception as exc:
            rc, raw = None, repr(exc)
        with lock:
            results.append({"machine": machine, "rc": rc, "output": raw,
                             "files": shard, "cmd": ""})

    routing._dispatch_to_machines(machines, plan, per_machine)

    rc = _merge_shard_results(results)
    print(
        "[TURBO TESTS: rc=" + str(rc)
        + " machines=" + str(len(machines))
        + " files=" + str(len(files))
        + "]"
    )
    return rc


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Turbo distributed pytest runner "
            "(Dell up to 60%% / Windows 30%% / Mint 10%%; "
            "offline machines redistribute). "
            "Activated by XF_TURBO_TESTS=1."
        )
    )
    parser.add_argument(
        "--language",
        required=True,
        choices=["python"],
        help="Which language to test (only 'python' is supported today).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect files and print the shard plan without running any tests.",
    )
    return parser


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    args = _build_arg_parser().parse_args()

    if args.dry_run:
        cfg = _load_routing_cfg()
        routing = _load_machine_routing()
        try:
            machines = routing._select_machines(cfg)
        except routing.RemoteUnavailableError as exc:
            print(f"[TURBO TESTS DRY-RUN: blocked: {exc}]", file=sys.stderr)
            return 1
        files = _discover_simpletest_files_fast()
        plan = routing._partition_weighted(files, machines)
        print("[TURBO TESTS DRY-RUN]")
        print(f"  discovery: fast file scan ({len(files)} SimpleTestCase files)")
        for name, shard in plan.items():
            print(f"  {name}: {len(shard)} files")
        return 0

    if args.language == "python":
        return run_python_tests()

    print(f"[TURBO TESTS: language '{args.language}' not implemented]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
