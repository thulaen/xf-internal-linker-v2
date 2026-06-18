#!/usr/bin/env python3
"""Distribute the read-only Python lint / type-check tools across machines.

Dell carries 100% of the changed-file lint load (config: ``lint_machines`` in
``config/mutation-routing.json``); Windows carries the rest. The three tools —
``ruff`` (which also carries the old error-only lint job via the PLE rules in
``backend/pyproject.toml``), ``mypy``, ``bandit`` — are read-only (no
database), so a machine only needs the source synced and the
``xf-linker-backend-quality`` image. There is nothing to merge into a database
and no test fixtures to load; a file is either clean or it is not.

``mypy`` runs through ``dmypy`` (the mypy daemon) inside a warm, persistent
container named ``xf-dmypy-daemon`` on the remote machine. The daemon keeps the
parsed-code state in memory between commits, so incremental type checks are
near-instant. The container is created once and reused; it is NEVER removed by
cleanup paths — surviving across runs is the whole point. The ``xf_lint_repo``
volume is re-synced by the sync step before tools run, so the daemon always
sees fresh files.

This mirrors the two existing sharders so the behaviour is identical and the
proven pieces are reused, not re-invented:

* the weighted split + fail-open machine selection come from the SINGLE shared
  ``scripts/machine_routing.py`` (Hamilton largest-remainder, ceiling clamp),
  the same module the mutation gate and the coverage gate import;
* the Dell push is the SAME ``tar -> alpine extract -> sha256 manifest`` hand-
  shake used by ``.githooks/check-scoped-mutation.py`` and
  ``.githooks/check-per-file-coverage.py``, into this gate's OWN named volume
  ``xf_lint_repo`` so the three gates never race on one volume.

Fail-CLOSED at the probe layer: if the configured Dell context does not answer
its reachability probe, ``machine_routing._select_machines`` raises and this gate
hard-fails with a "fix Dell" message — work is NEVER silently moved to Windows.
If Dell answers the probe but a slice's source sync or manifest verify fails
mid-run, that slice is re-linted locally and the fallback is announced on stdout
(``dell->local(unverified)``); the check still runs and the verdict is identical
in shape to the Dell path — only WHERE that slice is linted changes.

For LOCAL commits ``scripts/run-python-quality.sh`` defaults ``XF_LINT_SPLIT=1``
so Dell carries 100% of the changed-file lint load; CI keeps it off and lints in
the CI container. Set ``XF_LINT_SPLIT=0`` to force a local-only run.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Same tar exclude recipe the other two sharders use — the Dell side re-hashes
# the SAME bytes, so the exclude list MUST match exactly or the manifest fails.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _sync_tar_excludes import TAR_EXCLUDES as _TAR_EXCLUDES  # noqa: E402

# This gate's OWN source-snapshot volume on the remote machine, parallel to
# xf_mutation_repo / xf_coverage_repo so the three gates never collide.
_LINT_VOLUME = "xf_lint_repo"
_IMAGE = "xf-linker-backend-quality:latest"

# Mounts + env mirror the mutation run (check-scoped-mutation.py) EXACTLY so a
# tool resolves the same imports on Dell as it does locally — otherwise a tool
# could report a false `import-error` for a compiled extension that is present
# locally but missing on the remote. PYTHONPATH points at /repo/backend (the
# synced source on the remote) instead of the local /app bind mount.
_REMOTE_PYTHONPATH = "/opt/xf/compiled/active:/opt/xf/compiled:/repo/backend"

# The warm mypy-daemon container on the remote machine. NEVER remove it in a
# cleanup path — its in-memory parsed-code state surviving across runs is what
# makes incremental type checks near-instant. The ONE place it is removed on
# purpose is _run_mypy_self_healing, which resets it after a daemon crash so the
# next commit starts from a clean daemon (the crashed verdict is recomputed by a
# one-shot mypy in the same run).
_DMYPY_CONTAINER = "xf-dmypy-daemon"


def _inner_command(tool: str, files: list[str]) -> list[str]:
    """The tool invocation run INSIDE backend-quality, cwd=/repo/backend.

    File paths are backend-relative (e.g. ``apps/foo/bar.py``) on every machine,
    so the same command string is valid locally and on Dell. mypy goes through
    ``dmypy run`` so the warm daemon answers; ``--timeout 7200`` keeps the
    daemon alive for two idle hours before it shuts itself down (the container
    stays up and the next run restarts it transparently).
    """
    if tool == "ruff":
        return ["ruff", "check", *files]
    if tool == "mypy":
        return ["dmypy", "run", "--timeout", "7200", "--",
                "--config-file", "/repo/backend/mypy.ini", *files]
    if tool == "bandit":
        return ["bandit", "-q", *files]
    raise ValueError(f"Unknown lint tool: {tool!r} (expected ruff/mypy/bandit).")


def _load_machine_routing():
    """Import the shared machine-routing math by absolute path (single-sourced)."""
    path = REPO_ROOT / "scripts" / "machine_routing.py"
    spec = importlib.util.spec_from_file_location("machine_routing", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_lint_routing_config() -> dict:
    """Read the ``lint_machines`` block from config/mutation-routing.json.

    Falls back to a Dell-1.0 / Windows-0.0 pair (fail-closed: Dell does 100%,
    MSI 0%) if the key is absent so an older config never crashes the gate.
    """
    path = REPO_ROOT / "config" / "mutation-routing.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    machines = cfg.get("lint_machines")
    if not machines:
        machines = [
            {"name": "dell", "transport": "docker_context", "context": "dell",
             "weight": 1.0, "max_weight": 1.0},
        ]
    context_override = os.environ.get("XF_LINT_DOCKER_CONTEXT")
    if context_override:
        machines = [
            {
                **machine,
                "context": context_override,
            }
            for machine in machines
        ]
    return {"machines": machines}


def _host_hashes(rel_slice: list[str]) -> dict[str, str]:
    """sha256 of each backend/<rel> file the host ships to the remote."""
    hashes: dict[str, str] = {}
    for rel in rel_slice:
        try:
            data = (REPO_ROOT / "backend" / rel).read_bytes()
        except OSError:
            continue
        hashes[rel] = hashlib.sha256(data).hexdigest()
    return hashes


def _tar_producer(env: dict) -> subprocess.Popen:
    """One tar producer (backend + .githooks, shared exclude list) for the push."""
    return subprocess.Popen(
        ["tar", "-cf", "-", *_TAR_EXCLUDES, "backend", "rust", "services", ".githooks"],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )


def _remote_docker_cmd(context: str, *args: str) -> list[str]:
    """Return a command that runs Docker on the helper host through SSH."""
    if context == "__local__":
        return ["docker", *args]
    remote_command = "docker " + " ".join(shlex.quote(arg) for arg in args)
    return ["ssh", context, remote_command]


def _sync_source_to_context(context: str, env: dict) -> str | None:
    """Push a FULL source snapshot into xf_lint_repo on the remote context.

    ``ssh <host> docker run`` + alpine extracts the tar stream — the
    Compose layer is bypassed because it would resolve Windows bind-mount paths
    and send them to the remote Linux daemon. Returns None on success, else a
    plain-English error string.
    """
    extractor = _remote_docker_cmd(
        context,
        "run",
        "--rm",
        "-i",
        "-v", f"{_LINT_VOLUME}:/repo",
        "alpine:latest", "sh", "-c", "tar -xf - -C /repo",
    )
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
        return f"{context} source sync failed: tar or ssh not found on PATH."
    except subprocess.TimeoutExpired:
        return f"{context} source sync timed out after 5 minutes."
    if tar_rc != 0 or sink.returncode != 0:
        return f"{context} source sync failed:\n" + (out or "")
    return None


def _run_remote_sha(context: str, env: dict):
    """Return ``run_remote(rel_slice)->(rc,out)`` that sha256sums the remote copy."""
    def run_remote(rel_slice: list[str]) -> tuple[int, str]:
        cmd = _remote_docker_cmd(
            context,
            "run",
            "--rm",
            "-v", f"{_LINT_VOLUME}:/repo", "-w", "/repo/backend",
            "alpine:latest", "sh", "-c", "sha256sum " + " ".join(rel_slice),
        )
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
    """True only if the remote sha256 of every slice file matches the host's."""
    rc, out = run_remote(rel_slice)
    if rc != 0:
        return False
    remote: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            remote[parts[-1].replace("\\", "/")] = parts[0].strip()
    return all(remote.get(rel) == host_hashes.get(rel) for rel in rel_slice)


def _container_flags() -> list[str]:
    """Mounts + env shared by the one-shot lint containers and the dmypy daemon."""
    return [
        "-v", f"{_LINT_VOLUME}:/repo",
        "-v", "compiled_artifacts:/opt/xf/compiled",
        "-w", "/repo/backend",
        "-e", f"PYTHONPATH={_REMOTE_PYTHONPATH}",
        "-e", "DJANGO_SETTINGS_MODULE=config.settings.test",
        "-e", "DJANGO_SECRET_KEY=ci-fake-secret-key",
        "-e", "POSTGRES_PASSWORD=ci-fake-postgres-password",
        "-e", "REPO_ROOT=/repo",
    ]


def _ensure_dmypy_container(context: str) -> str | None:
    """Make sure the warm dmypy daemon container is running on the remote.

    Returns None when the container is running (already or freshly started),
    else a plain-English error string. Fail-closed: when the daemon cannot
    start, mypy does not run at all — there is no local fallback.
    """
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    rc, out = _run(
        _remote_docker_cmd(
            context,
            "inspect",
            "-f",
            "{{.State.Running}}",
            _DMYPY_CONTAINER,
        ),
        env, timeout=60,
    )
    if rc == 0 and out.strip().lower() == "true":
        return None
    # A stopped or half-created container blocks the name; clear it first.
    _run(_remote_docker_cmd(context, "rm", "-f", _DMYPY_CONTAINER), env, timeout=60)
    rc, out = _run(
        _remote_docker_cmd(
            context,
            "run",
            "-d",
            "--name",
            _DMYPY_CONTAINER,
            "--restart",
            "unless-stopped",
            *_container_flags(),
            _IMAGE,
            "sleep",
            "infinity",
        ),
        env, timeout=120,
    )
    if rc != 0:
        return (f"could not start the dmypy daemon container on {context}; "
                f"mypy cannot run (fail-closed, no local fallback):\n{out}")
    return None


def _remote_lint_cmd(context: str, tool: str, files: list[str]) -> list[str]:
    """The SSH-to-helper command that lints one slice on the remote host.

    mypy execs into the warm ``xf-dmypy-daemon`` container so the dmypy daemon
    keeps its parsed-code state between commits; the other tools use one-shot
    ``ssh <host> docker run --rm`` containers.
    """
    if tool == "mypy":
        return _remote_docker_cmd(
            context,
            "exec",
            _DMYPY_CONTAINER,
            *_inner_command(tool, files),
        )
    return _remote_docker_cmd(
        context,
        "run",
        "--rm",
        *_container_flags(),
        _IMAGE,
        *_inner_command(tool, files),
    )


def _run(cmd: list[str], env: dict, timeout: int) -> tuple[int, str]:
    """Run a command, never raise; return (rc, combined-output)."""
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=timeout, env=env, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, f"lint command could not run: {exc}"
    return proc.returncode, proc.stdout + proc.stderr


# Output signatures that mean the mypy DAEMON broke, not that the code has a
# type error. These are mypy-internal failures: a corrupted incremental cache
# ("Daemon crashed! ... attribute 'mro' of 'TypeInfo' undefined") or an endless
# fine-grained dependency-propagation loop ("Max number of iterations (1000)
# reached"). Both live in the dmypy fine-grained engine and recur even on a
# freshly restarted daemon, but they cannot fire under a one-shot,
# non-incremental ``mypy`` run.
_DMYPY_CRASH_SIGNATURES = (
    "Daemon crashed!",
    "INTERNAL ERROR",
    "Max number of iterations",
)


def _is_dmypy_crash(rc: int, out: str) -> bool:
    """True when a mypy run failed because the daemon broke, not the code.

    rc 0 (clean) and rc 1 (real type errors found) are trusted as-is; only a
    higher rc paired with a known daemon-crash signature is treated as a
    daemon failure worth self-healing.
    """
    if rc in (0, 1):
        return False
    return any(sig in out for sig in _DMYPY_CRASH_SIGNATURES)


def _oneshot_mypy_cmd(context: str, files: list[str]) -> list[str]:
    """A non-daemon, non-incremental mypy run in a throwaway container.

    Plain ``mypy --no-incremental`` never enters the dmypy fine-grained
    incremental engine, so the daemon-only defects cannot fire. Slower than the
    warm daemon, used only as the crash fallback.
    """
    return _remote_docker_cmd(
        context,
        "run",
        "--rm",
        *_container_flags(),
        _IMAGE, "mypy", "--config-file", "/repo/backend/mypy.ini",
        "--no-incremental", *files,
    )


def _run_mypy_self_healing(context: str, files: list[str], env: dict
                           ) -> tuple[int, str]:
    """Run mypy on the warm daemon; self-heal on a daemon crash.

    The daemon is fast but its incremental engine has known internal-error
    modes. On a crash, the daemon is reset (so the NEXT commit starts from a
    clean daemon) and THIS verdict is taken from a one-shot, non-incremental
    mypy run that cannot hit those defects. A real type error (rc 1) is never
    retried — it is reported straight away.
    """
    rc, out = _run(_remote_lint_cmd(context, "mypy", files), env, timeout=600)
    if not _is_dmypy_crash(rc, out):
        return rc, out
    notice = ("[LINT SELF-HEAL: dmypy daemon crashed; reset it and re-ran mypy "
              "one-shot (--no-incremental) for a clean verdict]\n")
    sys.stdout.write(notice)
    _run(_remote_docker_cmd(context, "rm", "-f", _DMYPY_CONTAINER), env, timeout=60)
    fb_rc, fb_out = _run(_oneshot_mypy_cmd(context, files), env, timeout=900)
    return fb_rc, out + "\n" + notice + fb_out


def _lint_slice_on_remote(context: str, tool: str, files: list[str]
                          ) -> tuple[int, str] | None:
    """Sync source once, verify it, then lint the whole slice on the remote.

    Returns (rc, output), or None when the slice could not be trusted (sync or
    manifest verify failed). mypy additionally needs the warm dmypy daemon; if
    that container cannot start, the slice fails closed with a plain-English
    error instead of falling back to a cold local run. A daemon CRASH (not a
    type error) self-heals via a one-shot mypy run — see _run_mypy_self_healing.
    """
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    if _sync_source_to_context(context, env) is not None:
        return None
    if not _verify_snapshot(_run_remote_sha(context, env), files, _host_hashes(files)):
        return None
    if tool == "mypy":
        daemon_error = _ensure_dmypy_container(context)
        if daemon_error is not None:
            return 1, daemon_error
        return _run_mypy_self_healing(context, files, env)
    return _run(_remote_lint_cmd(context, tool, files), env, timeout=600)


def run_tool_sharded(tool: str, files: list[str]) -> tuple[int, str]:
    """Split ``files`` across machines, lint each slice, merge into one verdict.

    Overall rc for the tool is the max over slices (any non-zero = failure).
    Output is concatenated with a per-machine header so a failure is traceable
    to the machine that found it.
    """
    if not files:
        return 0, f"[LINT SPLIT: {tool} had no changed files]\n"
    routing = _load_machine_routing()
    machines = routing._select_machines(_load_lint_routing_config())
    plan = routing._partition_weighted(files, machines)

    results: dict[str, tuple[int, str]] = {}
    lock = threading.Lock()

    def per_machine(machine: dict, slice_files: list[str]) -> None:
        if machine["transport"] != "docker_context":
            with lock:
                results[machine["name"]] = (1, "transport not allowed; lint runs only on the Dell docker context")
            return
        outcome = _lint_slice_on_remote(machine.get("context", "dell"), tool, slice_files)
        where = machine["name"]
        if outcome is None:  # untrusted -> fail-closed
            outcome = (1, f"Dell source sync or manifest verification failed for {tool}.")
        with lock:
            results[machine["name"]] = outcome
            sys.stdout.write(f"[LINT SPLIT: {tool} on {where} -> {len(slice_files)} file(s)]\n")

    routing._dispatch_to_machines(machines, plan, per_machine)

    rc = max((r[0] for r in results.values()), default=0)
    body = "".join(
        f"----- {tool} @ {name} (rc={r[0]}) -----\n{r[1]}"
        for name, r in sorted(results.items())
        if r[1].strip()
    )
    return rc, body


def _append_evidence(evidence_out, **fields) -> None:
    """Append one QualityEvidence JSON-lines row via the shared writer.

    Loaded by absolute path (same pattern as machine_routing) so the row shape
    is IDENTICAL to what the in-container per-tool step writes — downstream
    evidence checks see no difference between the split and local paths.
    """
    path = REPO_ROOT / "scripts" / "write_quality_evidence.py"
    spec = importlib.util.spec_from_file_location("write_quality_evidence", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.append_evidence_row(evidence_out, **fields)


def _write_lint_evidence(evidence_out, tool: str, files: list[str], rc: int) -> None:
    """Record the sharded tool's merged verdict as one QualityEvidence row."""
    check_type = "security" if tool == "bandit" else "static_analysis"
    if not files:
        _append_evidence(
            evidence_out, check_type=check_type, status="passed", tool_name=tool,
            command=f"{tool} (no changed targets)",
            summary=f"No changed backend file needed {tool}.",
            failure_fingerprint=f"{tool}:no-changed-targets",
        )
        return
    passed = rc == 0
    _append_evidence(
        evidence_out, check_type=check_type,
        status="passed" if passed else "failed", tool_name=tool,
        command=f"run_lint_on_context.py --tool {tool} (sharded Dell 100%)",
        summary=f"Sharded {tool} {'passed' if passed else 'failed'} for changed backend files.",
        failure_fingerprint=f"{tool}:{rc}",
    )


def run_lint(
    tools: list[str],
    files: list[str],
    *,
    bandit_files: list[str] | None = None,
    evidence_out=None,
) -> int:
    """Run every requested tool sharded across machines; return the worst rc.

    bandit runs on ``bandit_files`` (application files only) when provided; the
    other tools run on ``files``. When ``evidence_out`` is set, each tool's
    merged verdict is appended as a QualityEvidence row.
    """
    from quality_cache import QualityCache
    cache = QualityCache(REPO_ROOT)
    worst = 0
    
    for tool in tools:
        tool_files = (bandit_files if tool == "bandit" and bandit_files is not None else files) or []
        if not tool_files:
            if evidence_out is not None:
                _write_lint_evidence(evidence_out, tool, [], 0)
            continue
            
        subjects = {
            f: cache.subject_hash_for_files([REPO_ROOT / "backend" / f])
            for f in tool_files
        }
        to_run, skipped = cache.filter(tool, subjects)
        
        if skipped:
            sys.stdout.write(f"[LINT CACHE: skipped {len(skipped)} unchanged files for {tool}]\n")
        if not to_run:
            sys.stdout.write(f"[LINT CACHE: all files unchanged for {tool}]\n")
            if evidence_out is not None:
                _write_lint_evidence(evidence_out, tool, tool_files, 0)
            continue
            
        rc, out = run_tool_sharded(tool, to_run)
        if out:
            try:
                sys.stdout.write(out)
            except UnicodeEncodeError:
                sys.stdout.buffer.write(out.encode('utf-8'))
        worst = max(worst, rc)
        sys.stdout.write(f"[LINT RESULT: {tool} rc={rc}]\n")
        
        if evidence_out is not None:
            _write_lint_evidence(evidence_out, tool, to_run, rc)
            
        if rc == 0:
            cache.record(tool, [subjects[f] for f in to_run])
            
    return worst


def _load_audit_ignores() -> tuple[list[str], list[str]]:
    """Return (pip_audit_ids, safety_ids) from the documented allowlist.

    The allowlist (``config/dependency-audit-allowlist.json``) tracks the
    advisories that have no safe fix yet, each with a plain-English reason and
    a concrete revisit condition and a matching paper-trail entry. Missing or
    malformed file means no ignores — the audit then blocks on every finding,
    which is the safe default.
    """
    path = REPO_ROOT / "config" / "dependency-audit-allowlist.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], []
    pip_ids = [e["id"] for e in data.get("pip_audit_ignore", []) if e.get("id")]
    safety_ids = [e["id"] for e in data.get("safety_ignore", []) if e.get("id")]
    return pip_ids, safety_ids


def _all_pip_audit_findings_ignored(out: str) -> bool:
    """Return True when pip-audit found only documented allowlist entries."""
    for line in out.splitlines():
        words = line.strip().split()
        if len(words) >= 6 and words[:1] == ["Found"] and words[4:5] == ["ignored"]:
            try:
                return int(words[1]) == int(words[5])
            except ValueError:
                return False
    return False


def _dependency_audit_effective_rc(tool: str, rc: int, out: str) -> int:
    """Return the audit verdict after documented allowlist handling."""
    if rc == 0:
        return 0
    if tool == "pip-audit" and _all_pip_audit_findings_ignored(out):
        return 0
    return rc


def _run_dependency_audit(evidence_out: Path | None) -> None:
    """Run pip-audit and safety check on Dell.

    A non-zero result writes a ``failed`` evidence row, so a requirements
    change must leave the dependency set clean or every flagged advisory must
    be in the documented allowlist (``config/dependency-audit-allowlist.json``)
    with a reason and revisit condition. Results are cached on the requirements
    files' content hash, so the Dell calls are skipped until a requirements
    file or tool config changes.
    """
    from quality_cache import QualityCache
    cache = QualityCache(REPO_ROOT)
    subject = cache.subject_hash_for_files([
        REPO_ROOT / "backend" / "requirements.txt",
        REPO_ROOT / "backend" / "requirements-dev.txt",
        REPO_ROOT / "config" / "dependency-audit-allowlist.json",
    ])
    pip_ignores, safety_ignores = _load_audit_ignores()
    pip_audit_cmd = ["pip-audit", "-r", "requirements.txt"]
    for vuln_id in pip_ignores:
        pip_audit_cmd += ["--ignore-vuln", vuln_id]
    safety_cmd = ["safety", "check", "-r", "requirements.txt", "--full-report"]
    for vuln_id in safety_ignores:
        safety_cmd += ["--ignore", vuln_id]
    audit_commands = [
        ("pip-audit", pip_audit_cmd),
        ("safety", safety_cmd),
    ]
    pending = [(t, c) for t, c in audit_commands if not cache.has_pass(t, subject)]
    if not pending:
        sys.stdout.write(
            "[LINT CACHE: dependency audit skipped — requirements unchanged]\n"
        )
        return
    routing = _load_machine_routing()
    machines = routing._select_machines(_load_lint_routing_config())
    dell_ctx = next(
        (m.get("context", "dell") for m in machines if m["name"] == "dell"),
        "dell",
    )
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    _sync_source_to_context(dell_ctx, env)

    for tool, cmd_args in pending:
        cmd = _remote_docker_cmd(
            dell_ctx,
            "run",
            "--rm",
            "-v", f"{_LINT_VOLUME}:/repo", "-w", "/repo/backend",
            _IMAGE, *cmd_args,
        )
        rc, out = _run(cmd, env, timeout=300)
        effective_rc = _dependency_audit_effective_rc(tool, rc, out)
        if out.strip():
            sys.stdout.write(f"----- {tool} @ dell (rc={rc}) -----\n{out}\n")
        if effective_rc == 0:
            cache.record(tool, [subject])
        if evidence_out:
            _append_evidence(
                evidence_out,
                check_type="security",
                status="passed" if effective_rc == 0 else "failed",
                tool_name=tool, command=f"{tool} (Dell context)",
                summary=(
                    f"{tool} {'passed' if effective_rc == 0 else 'failed'} "
                    "for backend dependencies."
                ),
                failure_fingerprint=f"{tool}:{effective_rc}",
            )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tool", action="append", dest="tools",
        choices=["ruff", "mypy", "bandit"],
        help="Lint tool to run (repeatable). Default: all three.",
    )
    parser.add_argument(
        "--files", nargs="*", default=[],
        help="backend-relative Python file paths to lint (e.g. apps/foo/bar.py).",
    )
    parser.add_argument(
        "--bandit-files", nargs="*", default=None,
        help="backend-relative app files for bandit only (omit to reuse --files).",
    )
    parser.add_argument(
        "--evidence-out", default=None,
        help="JSON-lines path; when set, append one QualityEvidence row per tool.",
    )
    parser.add_argument(
        "--dependency-audit", action="store_true",
        help="Run pip-audit and safety check on Dell.",
    )
    return parser.parse_args(argv)


def _norm(values) -> list[str]:
    return [v.replace("\\", "/").removeprefix("backend/") for v in (values or []) if v.strip()]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv if argv is not None else sys.argv[1:]))
    tools = args.tools or ["ruff", "mypy", "bandit"]
    files = _norm(args.files)
    bandit_files = None if args.bandit_files is None else _norm(args.bandit_files)
    evidence_out = Path(args.evidence_out) if args.evidence_out else None
    rc = 0
    if not files and not bandit_files:
        sys.stdout.write("[LINT SPLIT: no changed files — nothing to lint]\n")
    else:
        rc = run_lint(tools, files, bandit_files=bandit_files, evidence_out=evidence_out)
    if args.dependency_audit:
        _run_dependency_audit(evidence_out)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
