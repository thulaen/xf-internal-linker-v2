#!/usr/bin/env python3
"""Scoped, DIFF-AWARE mutation testing on EDITED lines only — hard block.

Mutation testing changes small pieces of your code (a `+` becomes a `-`,
a `True` becomes a `False`) and re-runs the tests. If the tests still pass,
the mutant "survived" — meaning your tests did not actually check that line.

This gate runs mutation ONLY on the staged files AND judges the result ONLY on
the lines THIS commit changed (diff mutation), via the two-phase helper
`_mutmut_diff_scope.py`: generate every mutant fast with a no-op runner, keep
only the ones on changed lines, then test ONLY those with the real runner. A
surviving mutant on a changed line is a hard block; untouched-legacy survivors
are ignored. This mirrors the diff-coverage gate.

WHERE IT RUNS:
  All three machines (Windows, Mint, Dell) run via docker_context or SSH transport.

Tooling: mutmut is pinned to 2.x (3.x trampolines re-trigger
multiprocessing.set_start_method and cannot baseline intra-module calls).
Go / C++ / Rust mutation run in their own scoped runners in
scripts/precommit-docker.sh; this gate does not duplicate them.

Exit codes:
    0 — no surviving mutant on any changed line (or no Python source staged /
        no executable changed lines / no test to scope to).
    1 — a mutant survived on a changed line, or mutation could not run.
"""

from __future__ import annotations

import atexit
import hashlib
import importlib.util
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]

# Cap how many files one commit mutates so the hook can't run for an hour.
_MAX_FILES = 15

# Crash-safety layer (TASK #10) ───────────────────────────────────────────────
# A killed commit (Windows has no process-group SIGKILL propagation) used to
# leave orphan mutmut containers mutating staged files in place; the final
# _restore never ran, stranding mutants in the working tree. The lockfile +
# orphan-container sweep + index-restore backstop below close that hole.
_LOCK_PATH = REPO_ROOT / ".git" / "xf-scoped-mutation.lock"

# Every mutation container carries this label so a crash sweep can find + kill
# them by label alone, with no record of their ids on disk.
_MUTATION_LABEL = "xf.mutation=scoped"

# Files this process restores from the git index at exit / on a crash sweep.
# Populated once the staged file list is known so the signal/atexit handlers,
# which take no arguments, know what to roll back.
_GUARDED_REL_PATHS: list[str] = []

# The ONE tar exclude recipe shared by every remote source push (Dell + Mint).
# The remote re-hash must hash the SAME bytes, so this list lives in one place.
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _sync_tar_excludes import TAR_EXCLUDES as _TAR_EXCLUDES  # noqa: E402


def _load_coverage_hook():
    """Reuse the test-discovery + changed-line helpers from the coverage hook (DRY)."""
    path = Path(__file__).with_name("check-per-file-coverage.py")
    spec = importlib.util.spec_from_file_location("check_per_file_coverage", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_machine_routing():
    """Import the shared machine-routing math by absolute path (single-sourced)."""
    path = REPO_ROOT / "scripts" / "machine_routing.py"
    spec = importlib.util.spec_from_file_location("machine_routing", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _host_hashes(rel_slice: list[str]) -> dict[str, str]:
    """sha256 of each backend/<rel> file the host will ship to a remote.

    Keyed by the backend-relative path so the remote can recompute the same
    digest over its synced copy and the two are compared file-by-file.
    """
    hashes: dict[str, str] = {}
    for rel in rel_slice:
        try:
            data = (REPO_ROOT / "backend" / rel).read_bytes()
        except OSError:
            continue
        hashes[rel] = hashlib.sha256(data).hexdigest()
    return hashes


def _manifest_digest(host_hashes: dict[str, str]) -> str:
    """Order-independent digest of a host-hash manifest (for logging/compare)."""
    joined = "\n".join(f"{k} {host_hashes[k]}" for k in sorted(host_hashes))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _verify_snapshot(
    run_remote: Callable[[list[str]], tuple[int, str]],
    rel_slice: list[str],
    host_hashes: dict[str, str],
) -> bool:
    """True only if the remote's sha256 of every slice file matches the host.

    `run_remote(rel_slice) -> (rc, output)` runs `sha256sum <rel...>` inside the
    remote's synced /repo/backend. A non-zero rc, a missing file, or any single
    mismatch makes the snapshot UNVERIFIED, so the slice is never trusted.
    """
    rc, out = run_remote(rel_slice)
    if rc != 0:
        return False
    remote: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            remote[parts[-1].replace("\\", "/")] = parts[0].strip()
    return all(remote.get(rel) == host_hashes.get(rel) for rel in rel_slice)


def _fail(detail: str) -> int:
    sys.stderr.write(
        "\nFAIL check-scoped-mutation: a mutant survived on a line you changed.\n"
        "WHY: mutation testing altered a line THIS commit edited and the tests "
        "still passed — so that change is not really tested. This gate judges "
        "only the lines you changed, never the whole legacy file.\n"
        "UNBLOCK: add an assertion that fails when the listed mutant is applied "
        "(see `mutmut show <id>` in backend-quality), then re-stage.\n"
        f"\nDetail:\n{detail}\n"
    )
    return 1


def _staged_python_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    files = []
    for line in out.splitlines():
        p = line.strip().replace("\\", "/")
        if not p.startswith("backend/apps/") or not p.endswith(".py"):
            continue
        if re.search(r"(^|/)(tests?/|test_|tests_)|/migrations/|/__init__\.py$", p):
            continue
        files.append(p)
    return files[:_MAX_FILES]


def _snapshot(abs_paths: list[Path]) -> dict[Path, bytes]:
    snap: dict[Path, bytes] = {}
    for p in abs_paths:
        try:
            snap[p] = p.read_bytes()
        except OSError:
            pass
    return snap


def _restore(snap: dict[Path, bytes]) -> None:
    for p, data in snap.items():
        try:
            if p.read_bytes() != data:
                p.write_bytes(data)
        except OSError:
            pass


# ── crash-safety layer (TASK #10) ──────────────────────────────────────────────

def _pid_is_live(pid: int) -> bool:
    """True if a process with `pid` is still running (Windows + POSIX)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                text=True, encoding="utf-8", errors="replace",
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return False
        return str(pid) in out
    try:
        os.kill(pid, 0)  # signal 0 only checks existence, sends nothing
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    return True


def _read_lock_pid() -> int | None:
    """PID recorded in the lockfile, or None if absent/unreadable/garbage."""
    try:
        text = _LOCK_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _configured_sweep_contexts() -> list[str]:
    """Every docker context to sweep: local + each machine's configured context.

    Reads the machines' "context" fields from config/mutation-routing.json so any
    docker_context machine's orphans (Dell as well as Mint) are swept, not just
    Mint. Falls back to ["local", "mint", "dell"] when the config cannot be read.
    """
    contexts = ["local"]
    try:
        cfg = _load_routing_config()
    except (OSError, ValueError):
        return ["local", "mint", "dell"]
    for machine in cfg.get("machines", []):
        ctx = machine.get("context")
        if ctx and ctx != "local" and ctx not in contexts:
            contexts.append(ctx)
    return contexts if len(contexts) > 1 else ["local", "mint", "dell"]


def _sweep_orphan_containers() -> None:
    """Force-remove every mutation container left behind by a crashed run.

    Finds containers by the `xf.mutation=scoped` label only — no ids are kept
    on disk — and removes them locally AND on every configured docker context
    (Dell + Mint, read from config/mutation-routing.json) so a daemon-side
    orphan can never keep mutating after the hook process dies.
    """
    contexts = _configured_sweep_contexts()
    for ctx in contexts:
        prefix = [] if ctx == "local" else ["--context", ctx]
        try:
            out = subprocess.check_output(
                ["docker", *prefix, "ps", "-aq", "--filter", f"label={_MUTATION_LABEL}"],
                text=True, encoding="utf-8", errors="replace", timeout=60,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError,
                subprocess.TimeoutExpired):
            continue
        ids = [cid for cid in out.split() if cid]
        if not ids:
            continue
        try:
            subprocess.run(
                ["docker", *prefix, "rm", "-f", *ids],
                check=False, timeout=120, capture_output=True,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue


def _restore_from_index(rel_paths: list[str]) -> None:
    """Drop any stranded mutant by restoring each staged file from the index.

    The git INDEX is the source of truth here, not a Python snapshot: a crashed
    previous run never recorded a snapshot, so `git checkout -- <path>` is the
    only backstop that returns the staged source to exactly what was committed.
    """
    for rel in rel_paths:
        path = f"backend/{rel}" if not rel.startswith("backend/") else rel
        try:
            subprocess.run(
                ["git", "checkout", "--", path],
                cwd=REPO_ROOT, check=False, timeout=60, capture_output=True,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue


def _crash_cleanup() -> None:
    """atexit / signal backstop: restore staged files, drop lock, sweep orphans."""
    _restore_from_index(_GUARDED_REL_PATHS)
    _sweep_orphan_containers()
    try:
        _LOCK_PATH.unlink()
    except OSError:
        pass


def _signal_cleanup(signum, _frame) -> None:
    """Run the crash backstop then re-raise the default action for `signum`."""
    _crash_cleanup()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _acquire_lock_or_heal(rel_paths: list[str]) -> int:
    """Acquire the run lock; self-heal a stale lock; abort on a live lock.

    Returns 0 when the lock is held and handlers are armed, or 2 (Rule-F abort)
    when another live run owns the lock. A stale lock means the previous run
    crashed: sweep orphan containers, restore staged files from the index, then
    take the lock and continue.
    """
    existing = _read_lock_pid()
    if existing is not None and _pid_is_live(existing):
        sys.stderr.write(
            "\nFAIL check-scoped-mutation: another mutation run is already in "
            f"progress (pid {existing}).\n"
            "WHY: two mutation runs at once would mutate the same staged files "
            "in place and corrupt each other's source.\n"
            "UNBLOCK: wait for the other commit to finish, or if it is dead "
            f"delete the stale lock at {_LOCK_PATH} and re-stage.\n"
        )
        return 2
    if existing is not None:
        _sweep_orphan_containers()
        _restore_from_index(rel_paths)
    _GUARDED_REL_PATHS[:] = rel_paths
    try:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    atexit.register(_crash_cleanup)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _signal_cleanup)
        except (ValueError, OSError):
            pass  # not on the main thread / unsupported platform signal
    return 0


def _changed_token(rel: str, lines: set[int] | None) -> str | None:
    """Build a `path:line,line` (or `path:ALL`) token for the helper."""
    if lines is None:  # brand-new file → every line is changed code
        return f"{rel}:ALL"
    if not lines:
        return None
    return f"{rel}:" + ",".join(str(n) for n in sorted(lines))


_TEST_NAME_TEMPLATES = ("tests_{stem}.py", "tests/test_{stem}.py", "test_{stem}.py")


def _convention_tests(rel: str) -> list[str]:
    """Backend-relative test files for one source file by NAMING CONVENTION.

    Deliberately NOT `cov._test_paths_for`: that also appends every OTHER test
    staged in the same app (correct for coverage, wrong here). mutmut re-runs
    the runner once per mutant, so scoping a file's mutants to unrelated app
    tests (including slow DB suites) is the difference between a feasible gate
    and a 30-minute timeout. A file's mutants only die to a test that exercises
    it, and the `test_<stem>.py` companion is that test."""
    src = Path(rel)
    stem = src.stem
    found: list[str] = []
    cur = src.parent
    while True:
        for tmpl in _TEST_NAME_TEMPLATES:
            cand = cur / tmpl.format(stem=stem)
            posix = cand.as_posix()
            if (REPO_ROOT / "backend" / cand).is_file() and posix not in found:
                found.append(posix)
        parts = cur.parts
        if len(parts) == 0 or parts[0] != "apps" or len(parts) <= 1:
            break
        cur = cur.parent
    return found


def _tests_map(cov, rel_paths: list[str]) -> dict[str, list[str]]:
    """Map each source file -> ONLY its own convention test files.

    Per-file scoping (not the flat union) is what keeps the mutation gate under
    its time budget: mutmut re-runs the runner once per mutant, so each file's
    mutants must test against only that file's (often fast) tests."""
    return {rel: _convention_tests(rel) for rel in rel_paths}


def _flatten_tests(tests_map: dict[str, list[str]]) -> list[str]:
    """De-duplicated union of every file's tests (the --tests fallback)."""
    union: list[str] = []
    for tests in tests_map.values():
        for t in tests:
            if t not in union:
                union.append(t)
    return union


def _helper_argv(
    files: list[str],
    test_paths: list[str],
    tokens: list[str],
    tests_map: dict[str, list[str]],
) -> list[str]:
    map_tokens = [f"{rel}::{','.join(tests)}" for rel, tests in tests_map.items()]
    return [
        "python", "/repo/.githooks/_mutmut_diff_scope.py",
        "--paths", ",".join(files),
        "--tests", " ".join(test_paths),
        "--tests-map", *map_tokens,
        "--changed", *tokens,
    ]


def _parse_live(raw: str) -> list[str] | None:
    if "DONE" not in raw and "NO_CHANGED_MUTANTS" not in raw:
        return None  # helper did not complete
    return [
        ln[len("LIVE "):].strip()
        for ln in raw.splitlines()
        if ln.startswith("LIVE ")
    ]


def _tar_producer(env: dict) -> subprocess.Popen:
    """One tar producer (backend + .githooks, shared exclude list) for any remote.

    Dell and Mint pipe THIS exact byte stream into their extractor, so the
    remote always receives — and can re-hash — the identical source the host
    measured. Sharing one producer is what keeps the Mint push from drifting
    back into the partial-copy condition that originally banned it.
    """
    return subprocess.Popen(
        ["tar", "-cf", "-", *_TAR_EXCLUDES, "backend", ".githooks"],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )


def _pipe_tar_into(extractor: list[str], env: dict, who: str) -> str | None:
    """Pipe `_tar_producer` into `extractor`; return None on success else error.

    BOTH the tar producer's and the extractor's exit codes are checked so a
    half-finished copy is reported as a sync failure (never silently trusted).
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


def _purge_remote_mutmut_cache(context: str, env: dict) -> None:
    """Delete any `.mutmut-cache` left in the remote named volume by a prior run.

    `xf_mutation_repo` is a PERSISTENT named volume on the remote machine. The
    tar sync overwrites `backend/` source but never carries `.mutmut-cache`
    (it is not part of the source), so a cache written by a PREVIOUS commit's
    run survives in the volume. mutmut then reuses those stale verdicts against
    freshly-synced source and silently reports different survivors than a clean
    local run (observed: Dell disagreed with the host — K8S.26 §14). Purging the
    cache right after extraction — before the manifest check and the run — makes
    every remote run start clean, exactly like the local `--rm` container does.

    `rm -rf` covers both cache shapes (mutmut 2.5.1 writes a file; some versions
    write a directory). Best-effort: a purge failure is WARNED on stderr (never
    swallowed) so a recurrence of the divergence is visible, but it does not
    block — the manifest handshake still guards source integrity.
    """
    cleaner = [
        "docker", "--context", context, "run", "--rm",
        "-v", "xf_mutation_repo:/repo",
        "alpine:latest", "sh", "-c", "rm -rf /repo/backend/.mutmut-cache",
    ]
    try:
        proc = subprocess.run(
            cleaner, cwd=REPO_ROOT, text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=60, env=env,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"WARN {context} .mutmut-cache purge could not run: {exc}", file=sys.stderr)
        return
    if proc.returncode != 0:
        print(
            f"WARN {context} .mutmut-cache purge exited {proc.returncode}: "
            f"{(proc.stdout + proc.stderr).strip()}",
            file=sys.stderr,
        )


def _sync_source_to_mint(context: str, env: dict) -> str | None:
    """Push a FULL source snapshot into a named volume on any docker_context machine.

    Uses bare `docker run` with the named volume `xf_mutation_repo` — the
    Compose layer is bypassed entirely because it would resolve Windows bind-mount
    paths (``./backend:/app``) and send them to the remote Linux daemon, which
    rejects them. The alpine image extracts the tar stream so no pre-built quality
    image is required at sync time; only the mutation run step needs it.
    The manifest handshake that follows proves the copy is byte-identical before
    any result is trusted.

    After a successful extraction the stale `.mutmut-cache` from any prior run on
    the persistent named volume is purged, so the remote run starts clean and its
    survivors match a fresh local run.
    """
    extractor = [
        "docker", "--context", context, "run", "--rm", "-i",
        "-v", "xf_mutation_repo:/repo",
        "alpine:latest", "sh", "-c", "tar -xf - -C /repo",
    ]
    sync_error = _pipe_tar_into(extractor, env, context)
    if sync_error is not None:
        return sync_error
    _purge_remote_mutmut_cache(context, env)
    return None


def _mint_run_remote(context: str, env: dict) -> Callable[[list[str]], tuple[int, str]]:
    """Return a `run_remote(rel_slice)->(rc,out)` that sha256sums the Mint copy."""
    def run_remote(rel_slice: list[str]) -> tuple[int, str]:
        cmd = (
            "docker", "--context", context, "run", "--rm",
            "-v", "xf_mutation_repo:/repo",
            "-w", "/repo/backend",
            "alpine:latest", "sh", "-c",
            "sha256sum " + " ".join(rel_slice),
        )
        try:
            proc = subprocess.run(
                list(cmd), cwd=REPO_ROOT, text=True, encoding="utf-8",
                errors="replace", capture_output=True, timeout=120, env=env,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 1, f"{context} manifest handshake could not run."
        return proc.returncode, proc.stdout + proc.stderr
    return run_remote


def _run_mutmut_on_context(
    helper: list[str], rel_slice: list[str], context: str
) -> tuple[list[str] | None, str]:
    """Run one slice's helper on a named docker context AFTER a verified push.

    `context` is the machine's OWN docker context (e.g. "dell" or "mint"), so a
    Dell-owned slice runs on Dell and a Mint-owned slice runs on Mint — the gate
    no longer hardcodes one remote. Order is strict: full tar push → remote
    sha256 manifest must match the host → only then run the helper. Any sync or
    verify failure returns (None, error) so the caller re-runs the slice on the
    trusted local runner; remote results are never trusted on an unverified copy.
    """
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    sync_problem = _sync_source_to_mint(context, env)
    if sync_problem is not None:
        return None, sync_problem
    if not _verify_snapshot(_mint_run_remote(context, env), rel_slice, _host_hashes(rel_slice)):
        return None, f"{context} snapshot manifest did not match the host; slice not trusted."
    name = f"xf-mutation-{context}-{os.getpid()}"
    cmd = [
        "docker", "--context", context, "run", "--rm",
        "--name", name, "--label", _MUTATION_LABEL,
        "-v", "xf_mutation_repo:/repo",
        "-v", "compiled_artifacts:/opt/xf/compiled",
        "--network", "xf-internal-linker-v2_default",
        "-w", "/repo/backend",
        "-e", "DJANGO_SETTINGS_MODULE=config.settings.test",
        "-e", "PYTHONPATH=/opt/xf/compiled/active:/opt/xf/compiled:/app",
        "-e", "REPO_ROOT=/repo",
        "xf-linker-backend-quality:latest",
        *helper,
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=3600, env=env,
        )
    except FileNotFoundError:
        return None, f"Docker context '{context}' not available for mutation."
    except subprocess.TimeoutExpired:
        _force_remove_container(name, context)
        return None, f"{context.title()} mutation run exceeded 60 minutes and was stopped."
    raw = proc.stdout + proc.stderr
    return _parse_live(raw), raw


def _run_mutmut_on_mint(
    helper: list[str], rel_slice: list[str]
) -> tuple[list[str] | None, str]:
    """Back-compat wrapper: run the slice on the Mint docker context.

    Kept so existing call sites and tests that name the Mint runner still work;
    it just forwards to the context-aware runner with the Mint context.
    """
    return _run_mutmut_on_context(helper, rel_slice, os.environ.get("MINT_CONTEXT", "mint"))


def _local_run(
    rel_paths: list[str],
    tokens: list[str],
    tests_map: dict[str, list[str]],
) -> tuple[list[str] | None, str]:
    """Run a slice on the always-trusted local Windows backend-quality.

    Snapshots + force-restores the bind-mounted targets (mutmut mutates in
    place). Used both for the bare-local mode and to RE-JUDGE any remote slice
    that failed sync/verify/completion — the blast radius of a broken remote is
    capped at today's single-machine local gate.
    """
    test_paths = _flatten_tests({r: tests_map.get(r, []) for r in rel_paths})
    if not test_paths:
        return None, "No test file found for the local slice; cannot run mutation."
    helper = _helper_argv(rel_paths, test_paths, tokens, tests_map)
    name = f"xf-mutation-{os.getpid()}"
    cmd = [
        "docker", "compose", "run", "--rm", "-T", "--name", name,
        "--label", _MUTATION_LABEL, "-w", "/repo/backend",
        "backend-quality", *helper,
    ]
    abs_targets = [REPO_ROOT / "backend" / r for r in rel_paths]
    snap = _snapshot(abs_targets)
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=3600, env=env,
        )
    except FileNotFoundError:
        return None, "Docker is not available; mutation could not run."
    except subprocess.TimeoutExpired:
        _force_remove_container(name)
        return None, "Mutation run exceeded 60 minutes and was stopped."
    finally:
        _restore(snap)
    raw = proc.stdout + proc.stderr
    return _parse_live(raw), raw


def _force_remove_container(name: str, context: str | None = None) -> None:
    """Kill a daemon-side mutation container that outlived its subprocess.

    subprocess.run timing out only kills the local `docker` client; the
    container keeps running (and keeps mutating staged files) until removed by
    name on the daemon. This is the timeout backstop for that orphan.
    """
    prefix = ["--context", context] if context else []
    try:
        subprocess.run(
            ["docker", *prefix, "rm", "-f", name],
            check=False, timeout=60, capture_output=True,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass


def _slice_tokens(files: list[str], token_by_rel: dict[str, str]) -> list[str]:
    """Changed-line tokens for exactly the files in this slice (index-aligned)."""
    return [token_by_rel[r] for r in files if r in token_by_rel]


def _run_slice_on_machine(
    machine: dict,
    files: list[str],
    token_by_rel: dict[str, str],
    tests_map: dict[str, list[str]],
) -> tuple[list[str] | None, str]:
    """Run one disjoint file slice on its owning machine by transport.

    docker_local   → trusted local runner (snapshot/restore).
    docker_context → any remote context machine (Dell or Mint), after a verified
                     full-source push via the shared named volume xf_mutation_repo.
    """
    tokens = _slice_tokens(files, token_by_rel)
    slice_map = {r: tests_map.get(r, []) for r in files}
    test_paths = _flatten_tests(slice_map)
    transport = machine["transport"]
    if transport == "docker_local":
        return _local_run(files, tokens, slice_map)
    helper = _helper_argv(files, test_paths, tokens, slice_map)
    if transport == "docker_context":
        context = machine.get("context", "mint")
        return _run_mutmut_on_context(helper, files, context)
    return None, f"Unknown transport '{transport}' for machine {machine['name']}."


def _merge_machine_results(
    results: dict[str, tuple[list[str] | None, str, list[str]]],
    token_by_rel: dict[str, str],
    tests_map: dict[str, list[str]],
    expected_files: set[str],
) -> tuple[list[str] | None, str]:
    """Union confirmed survivors; re-judge any failed/None slice locally.

    `results[name] = (live_or_None, raw, files)`. A completing machine
    (live is a list) contributes its survivors to the union. A machine whose
    run did NOT complete (live is None) is NOT trusted: its files re-run on the
    local runner, and only if the LOCAL re-run ALSO fails to complete does the
    whole gate hard-fail (return None) — a broken remote can never be a pass.

    `expected_files` is every file that was dispatched. If any of them was
    never judged (a machine thread vanished without recording a result), the
    gate hard-fails (return None) rather than reporting a false 0-survivor pass.
    """
    union: list[str] = []
    raws: list[str] = []
    judged: set[str] = set()
    for name, (live, raw, files) in results.items():
        raws.append(f"[{name}]\n{raw}")
        if live is not None:
            union.extend(live)
            judged.update(files)
            continue
        re_live, re_raw = _local_run(files, _slice_tokens(files, token_by_rel),
                                     {r: tests_map.get(r, []) for r in files})
        raws.append(f"[{name}->local-recover]\n{re_raw}")
        if re_live is None:
            return None, "\n\n".join(raws)  # nothing could judge this slice
        union.extend(re_live)
        judged.update(files)
    missing = expected_files - judged
    if missing:
        raws.append("UNJUDGED FILES (no machine returned a verdict): "
                    + ", ".join(sorted(missing)))
        return None, "\n\n".join(raws)
    return union, "\n\n".join(raws)


def _run_mutmut_split(
    rel_paths: list[str],
    token_by_rel: dict[str, str],
    tests_map: dict[str, list[str]],
    run_one: Callable[..., tuple[list[str] | None, str]] | None = None,
    select: Callable[..., list[dict]] | None = None,
    partition: Callable[..., dict[str, list]] | None = None,
) -> tuple[list[str] | None, str]:
    """Weighted 3-machine fan-out of the staged files (XF_MUTATION_SPLIT=1).

    Selects reachable machines (Dell ≤60% ceiling / Windows 30% / Mint 10%;
    powered-off boxes dropped + redistributed), partitions the files into
    DISJOINT slices, runs each slice on its owning machine in parallel, then
    UNIONs the confirmed survivors. Any remote that fails sync/verify/completion
    is re-judged locally; only a local failure hard-fails the gate.
    """
    routing = _load_machine_routing()
    run_one = run_one or _run_slice_on_machine
    select = select or routing._select_machines
    partition = partition or routing._partition_weighted

    cfg = _load_routing_config()
    machines = select(cfg)
    plan = partition(rel_paths, machines)

    results: dict[str, tuple[list[str] | None, str, list[str]]] = {}
    lock = threading.Lock()

    def per_machine(machine: dict, files: list[str]) -> None:
        # A crashed thread must NOT vanish silently. If run_one raises anything
        # the inner subprocess wrappers did not catch (broken pipe, EMFILE,
        # PermissionError, ...), record None so _merge_machine_results re-judges
        # the slice locally — never let an unjudged changed line become a pass.
        try:
            live, raw = run_one(machine, files, token_by_rel, tests_map)
        except Exception as exc:  # noqa: BLE001 - fail closed on any thread crash
            live, raw = None, f"{machine['name']} crashed: {exc!r}"
        with lock:
            results[machine["name"]] = (live, raw, files)

    expected = {f for slice_files in plan.values() for f in slice_files}
    routing._dispatch_to_machines(machines, plan, per_machine)
    return _merge_machine_results(results, token_by_rel, tests_map, expected)


def _load_routing_config() -> dict:
    """Read config/mutation-routing.json (same file the turbo sweep reads)."""
    import json
    path = REPO_ROOT / "config" / "mutation-routing.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _run_mutmut(
    rel_paths: list[str], changed_tokens: list[str]
) -> tuple[list[str] | None, str]:
    """Drive the two-phase diff-scope helper. Two modes, dispatched in order.

    (1) XF_MUTATION_SPLIT=1 → weighted 3-machine fan-out, (2) default →
        today's single local backend-quality run.

    Returns (live_survivors, raw): the list of 'path:line (mutant id)' strings
    that survived on a changed line, or None if mutation could not run.
    """
    cov = _load_coverage_hook()
    tests_map = _tests_map(cov, rel_paths)
    test_paths = _flatten_tests(tests_map)
    if not test_paths:
        return None, (
            "No test file found for the staged source files; cannot run "
            "mutation without tests to scope the runner to."
        )

    token_by_rel = _token_by_rel(rel_paths, changed_tokens)
    if os.environ.get("XF_MUTATION_SPLIT", "").strip() == "1":
        return _run_mutmut_split(rel_paths, token_by_rel, tests_map)
    return _local_run(rel_paths, changed_tokens, tests_map)


def _token_by_rel(rel_paths: list[str], changed_tokens: list[str]) -> dict[str, str]:
    """Map each rel path to its changed-line token (path:line,... before ':').

    The legacy flat `changed_tokens` list drops files with no changed lines, so
    it is NOT index-aligned with rel_paths. Keying by the token's path prefix
    rebuilds the per-file map the split path needs without that drift.
    """
    by_rel: dict[str, str] = {}
    for token in changed_tokens:
        rel = token.split(":", 1)[0]
        by_rel[rel] = token
    return by_rel


def main() -> int:
    staged = _staged_python_files()
    if not staged:
        return 0
    cov = _load_coverage_hook()

    changed_tokens: list[str] = []
    rel_paths: list[str] = []
    any_changed = False
    for p in staged:
        rel = p[len("backend/"):]
        rel_paths.append(rel)
        token = _changed_token(rel, cov._changed_lines(p))
        if token is not None:
            changed_tokens.append(token)
            any_changed = True
    if not any_changed:
        return 0  # only comments / blank / deleted lines — nothing to mutate-check

    lock_rc = _acquire_lock_or_heal(rel_paths)
    if lock_rc != 0:
        return lock_rc

    live, raw = _run_mutmut(rel_paths, changed_tokens)
    if live is None:
        return _fail(f"Could not run mutation.\n{raw[-1500:]}")
    if live:
        shown = ", ".join(live[:15])
        return _fail(f"surviving mutants on changed lines: {shown}")

    sys.stdout.write(
        "[SCOPED MUTATION: diff-mode, 0 surviving mutants on changed lines, "
        f"files={len(staged)}]\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
