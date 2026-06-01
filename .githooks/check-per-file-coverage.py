#!/usr/bin/env python3
"""Per-staged-file DIFF coverage floor — hard block.

For every staged Python production file, this gate measures whether the lines
this commit ADDS or MODIFIES are exercised by the file's tests (run under
coverage inside the backend container). It does NOT demand whole-file coverage
of large legacy files — only the changed lines must be covered. This is the
standard "new code must be tested" rule (cf. diff-cover) and lets small fixes
land on under-tested legacy files without forcing a whole-file rewrite, while
still blocking genuinely untested new code.

Test discovery: the convention test files next to / at the app root of the
source (tests_<stem>.py, tests/test_<stem>.py, test_<stem>.py) PLUS any test
file staged in the same commit under the same app — so a regression suite added
alongside the fix (even with a descriptive, non-stem name) is honoured.

Non-Python languages (Angular .ts, C++, Go, Rust, Haskell) are covered by
their dedicated quality runners already in scripts/precommit-docker.sh.

Exit codes:
    0 — every staged Python file has its changed executable lines covered
        (or no measurable floor / no changed executable lines).
    1 — a changed line is uncovered, no test was found for changed code, or
        coverage could not be measured.
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = REPO_ROOT / "scripts" / "detect_changed_modules.py"

# The ONE tar exclude recipe shared with check-scoped-mutation: the Dell side
# re-hashes the SAME bytes, so the exclude list must match exactly.
_TAR_EXCLUDES = (
    "--exclude=__pycache__", "--exclude=*.pyc", "--exclude=*.so",
    "--exclude=build", "--exclude=build_*", "--exclude=.pytest_cache",
    "--exclude=.ruff_cache", "--exclude=htmlcov", "--exclude=backend/reports",
)

# Named volume that holds the Dell-side source snapshot (parallel to the
# mutation gate's xf_mutation_repo — coverage gets its own so the two gates
# never race on the same volume).
_COVERAGE_VOLUME = "xf_coverage_repo"

# Parse `coverage report --show-missing`: the trailing column is a comma list
# of line numbers / ranges, e.g. "69-74, 78, 90-92".
_REPORT_ROW_RE = re.compile(
    r"^(?P<name>[\w./\\-]+\.py)\s+\d+\s+\d+\s+(?:\d+\s+\d+\s+)?[\d.]+%\s+(?P<missing>[\d,\s-]*)$",
    re.MULTILINE,
)
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@", re.MULTILINE)


def _load_resolver():
    spec = importlib.util.spec_from_file_location("detect_changed_modules", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fail(detail: str) -> int:
    sys.stderr.write(
        "\nFAIL check-per-file-coverage: a changed line is not covered by tests.\n"
        "WHY: every line you ADD or MODIFY in a production file must be exercised "
        "by a test (diff coverage). Untested new code is where regressions hide. "
        "This gate measures only the lines you changed, not the whole legacy file.\n"
        "UNBLOCK: add or extend a test so the listed changed lines run, then "
        "re-stage. Tiers live in coverage-modules.yaml; this gate enforces them "
        "on changed lines.\n"
        f"\nDetail:\n{detail}\n"
    )
    return 1


def _staged_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _is_production_py(p: str) -> bool:
    if not p.endswith(".py"):
        return False
    if not (p.startswith("backend/apps/") or p.startswith("backend/config/")):
        return False
    return not re.search(r"(^|/)(tests?/|test_|tests_)|/migrations/|/__init__\.py$", p)


def _is_test_py(p: str) -> bool:
    return p.endswith(".py") and bool(re.search(r"(^|/)(test_|tests_)|/tests/", p))


def _app_root(rel: str) -> str | None:
    """Return 'backend/apps/<app>' for a path under it, else None."""
    parts = Path(rel).parts
    if len(parts) >= 3 and parts[:2] == ("backend", "apps"):
        return "/".join(parts[:3])
    if len(parts) >= 2 and parts[0] == "backend" and parts[1] == "config":
        return "backend/config"
    return None


def _changed_lines(rel: str) -> set[int] | None:
    """Return the set of line numbers this commit adds/modifies in *rel*.

    None means a brand-new file (treat every executable line as changed).
    """
    try:
        diff = subprocess.check_output(
            ["git", "diff", "--cached", "--unified=0", "--", rel],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    if "new file mode" in diff[:2000]:
        return None
    changed: set[int] = set()
    for m in _HUNK_RE.finditer(diff):
        start = int(m.group("start"))
        count = int(m.group("count") or "1")
        for ln in range(start, start + count):
            changed.add(ln)
    return changed


def _test_paths_for(rel: str) -> list[str]:
    path = Path(rel)
    stem = path.stem
    found: list[str] = []
    cur = path.parent
    while True:
        for cand in (
            cur / f"tests_{stem}.py",
            cur / "tests" / f"test_{stem}.py",
            cur / f"test_{stem}.py",
        ):
            posix = cand.as_posix()
            if (REPO_ROOT / cand).is_file() and posix not in found:
                found.append(posix)
        parts = cur.parts
        if len(parts) <= 3 or parts[:2] != ("backend", "apps"):
            break
        cur = cur.parent
    # Also honour any test staged in the same app this commit — a regression
    # suite added alongside the fix (even with a descriptive, non-stem name).
    # Shared by check-per-file-coverage AND check-scoped-mutation, so both
    # discover the same tests from one source of truth.
    app = _app_root(rel)
    if app:
        for t in _staged_files():
            if _is_test_py(t) and t.startswith(app + "/") and t not in found:
                found.append(t)
    return found


def _expand_ranges(spec: str) -> set[int]:
    out: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            if lo.isdigit() and hi.isdigit():
                out.update(range(int(lo), int(hi) + 1))
        elif chunk.isdigit():
            out.add(int(chunk))
    return out


def _coverage_script(rel_to_backend: str, test_paths: list[str]) -> str:
    """Build the shared `coverage erase/run/report` shell line for ONE file.

    Single-sourced so the local backend-quality run and the Dell docker-context
    run measure coverage the identical way — only WHERE it runs differs. Uses a
    unique COVERAGE_FILE per source stem so concurrent files never clobber each
    other's .coverage data.
    """
    pytest_args = " ".join(t[len("backend/"):] for t in test_paths)
    stem = rel_to_backend.replace("/", "_").replace(".", "_")
    cov_file = f"/tmp/.cov_{stem}"
    return (
        f"COVERAGE_FILE={cov_file} python -m coverage erase && "
        f"COVERAGE_FILE={cov_file} python -m coverage run -m pytest {pytest_args} "
        "-p no:randomly -q --no-cov --override-ini='addopts=' >/dev/null 2>&1; "
        f"COVERAGE_FILE={cov_file} python -m coverage report --show-missing "
        f"--include='{rel_to_backend}*'"
    )


def _parse_missing(stdout: str, rel_to_backend: str) -> set[int] | None:
    """Pull the missing-line set for *rel_to_backend* out of a coverage report."""
    for m in _REPORT_ROW_RE.finditer(stdout):
        if m.group("name").endswith(rel_to_backend.split("/")[-1]):
            return _expand_ranges(m.group("missing"))
    return None


def _missing_lines(rel_to_backend: str, test_paths: list[str]) -> set[int] | None:
    """Run the tests under coverage in the LOCAL backend-quality container; return
    the set of UNCOVERED (missing) line numbers for the file, or None if
    unmeasurable. This is the always-trusted Windows path used both by default and
    as the fail-open recovery when Dell is unreachable.
    """
    script = _coverage_script(rel_to_backend, test_paths)
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    try:
        # coverage/pytest live in the backend-quality image (the lean runtime
        # backend deliberately omits them), per the quality-tool-ownership rule.
        proc = subprocess.run(
            ["docker", "compose", "run", "--rm", "-T", "backend-quality",
             "bash", "-lc", script],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=600, env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return _parse_missing(proc.stdout, rel_to_backend)


# ── Dell 80% / Windows 20% two-machine split ────────────────────────────────────


def _load_machine_routing():
    """Import the shared machine-routing math by absolute path (single-sourced).

    Reuses the SAME _select_machines / _partition_weighted (Hamilton/largest-
    remainder) helpers the mutation gate uses, so the 80/20 split, the ceiling
    clamp, and the fail-open machine drop behave identically across both gates.
    """
    path = REPO_ROOT / "scripts" / "machine_routing.py"
    spec = importlib.util.spec_from_file_location("machine_routing", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_coverage_routing_config() -> dict:
    """Read the `coverage_machines` block from config/mutation-routing.json.

    Falls back to a hard-coded Dell-0.80 / Windows-0.20 pair if the key is
    absent so an older config never crashes the gate.
    """
    path = REPO_ROOT / "config" / "mutation-routing.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    machines = cfg.get("coverage_machines")
    if not machines:
        machines = [
            {"name": "dell", "transport": "docker_context", "context": "dell",
             "weight": 0.80, "max_weight": 0.80},
            {"name": "windows", "transport": "docker_local",
             "weight": 0.20, "max_weight": 1.0},
        ]
    return {"machines": machines}


def _host_hashes(rel_slice: list[str]) -> dict[str, str]:
    """sha256 of each backend/<rel> file the host ships to Dell (keyed by rel)."""
    hashes: dict[str, str] = {}
    for rel in rel_slice:
        try:
            data = (REPO_ROOT / "backend" / rel).read_bytes()
        except OSError:
            continue
        hashes[rel] = hashlib.sha256(data).hexdigest()
    return hashes


def _tar_producer(env: dict) -> subprocess.Popen:
    """One tar producer (backend + .githooks, shared exclude list) for the Dell push."""
    return subprocess.Popen(
        ["tar", "-cf", "-", *_TAR_EXCLUDES, "backend", ".githooks"],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )


def _sync_source_to_dell(context: str, env: dict) -> str | None:
    """Push a FULL source snapshot into the named volume on the Dell context.

    Bare `docker --context <ctx> run` + alpine extracts the tar stream into
    xf_coverage_repo — the Compose layer is bypassed because it would resolve
    Windows bind-mount paths and send them to the remote Linux daemon. Returns
    None on success, else a plain-English error string.
    """
    extractor = [
        "docker", "--context", context, "run", "--rm", "-i",
        "-v", f"{_COVERAGE_VOLUME}:/repo",
        "alpine:latest", "sh", "-c", "tar -xf - -C /repo",
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


def _dell_run_remote(context: str, env: dict):
    """Return `run_remote(rel_slice)->(rc,out)` that sha256sums the Dell copy."""
    def run_remote(rel_slice: list[str]) -> tuple[int, str]:
        cmd = [
            "docker", "--context", context, "run", "--rm",
            "-v", f"{_COVERAGE_VOLUME}:/repo", "-w", "/repo/backend",
            "alpine:latest", "sh", "-c", "sha256sum " + " ".join(rel_slice),
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


def _verify_dell_snapshot(run_remote, rel_slice: list[str],
                          host_hashes: dict[str, str]) -> bool:
    """True only if Dell's sha256 of every slice file matches the host's."""
    rc, out = run_remote(rel_slice)
    if rc != 0:
        return False
    remote: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            remote[parts[-1].replace("\\", "/")] = parts[0].strip()
    return all(remote.get(rel) == host_hashes.get(rel) for rel in rel_slice)


def _dell_coverage_cmd(context: str, rel_to_backend: str,
                       test_paths: list[str]) -> list[str]:
    """Build the `docker --context dell run` command that measures ONE file.

    Mounts the synced source volume + compiled_artifacts, joins the compose
    network so the test DB on Dell's postgres is reachable, and runs the SAME
    coverage script as the local path under config.settings.test.
    """
    script = _coverage_script(rel_to_backend, test_paths)
    return [
        "docker", "--context", context, "run", "--rm",
        "-v", f"{_COVERAGE_VOLUME}:/repo",
        "-v", "compiled_artifacts:/opt/xf/compiled",
        "--network", "xf-internal-linker-v2_default",
        "-w", "/repo/backend",
        "-e", "DJANGO_SETTINGS_MODULE=config.settings.test",
        "-e", "PYTHONPATH=/opt/xf/compiled/active:/opt/xf/compiled:/app",
        "-e", "REPO_ROOT=/repo",
        "xf-linker-backend-quality:latest",
        "bash", "-lc", script,
    ]


def _missing_lines_dell(context: str, rel_to_backend: str,
                        test_paths: list[str], env: dict) -> set[int] | None:
    """Measure ONE file's missing lines on the Dell context; None if unmeasurable."""
    cmd = _dell_coverage_cmd(context, rel_to_backend, test_paths)
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=600, env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return _parse_missing(proc.stdout, rel_to_backend)


def _measure_slice_on_dell(context: str, slice_files: list[tuple[str, list[str]]]
                           ) -> dict[str, set[int] | None] | None:
    """Sync source to Dell once, verify it, then measure every file in the slice.

    `slice_files` is a list of (rel_to_backend, test_paths). Returns
    {rel_to_backend -> missing_set_or_None}, or None if the whole slice could
    not be trusted (sync or manifest verify failed) so the caller re-runs it
    locally. Per-file None inside the dict means that one file was unmeasurable
    on Dell and must be re-judged locally.
    """
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    if _sync_source_to_dell(context, env) is not None:
        return None
    rel_slice = [rel for rel, _ in slice_files]
    if not _verify_dell_snapshot(_dell_run_remote(context, env), rel_slice,
                                 _host_hashes(rel_slice)):
        return None
    out: dict[str, set[int] | None] = {}
    for rel, tests in slice_files:
        out[rel] = _missing_lines_dell(context, rel, tests, env) if tests else None
    return out


def _measure_local(plan: list[tuple[str, list[str]]]) -> dict[str, set[int] | None]:
    """Measure every (rel, tests) on the always-trusted local Windows runner.

    A file with no tests maps to None (unmeasurable) — the floor evaluator turns
    that into the existing "no test found" verdict, so behaviour is unchanged.
    """
    return {
        rel: (_missing_lines(rel, tests) if tests else None)
        for rel, tests in plan
    }


def _measure_split(plan: list[tuple[str, list[str]]]
                   ) -> dict[str, set[int] | None]:
    """Partition Dell 80% / Windows 20%, measure each slice, merge the results.

    Fail-open at every layer: if no Dell context answers the probe, the routing
    helper collapses to a single local Windows machine and ALL files run locally.
    If Dell answers but its sync/verify fails, that slice is re-measured locally.
    The merged per-file missing-line map is identical in shape to the local-only
    path, so the floor evaluator (and therefore pass/fail) is unchanged.
    """
    routing = _load_machine_routing()
    cfg = _load_coverage_routing_config()
    machines = routing._select_machines(cfg)
    by_rel = {rel: tests for rel, tests in plan}
    rel_paths = [rel for rel, _ in plan]
    split = routing._partition_weighted(rel_paths, machines)

    merged: dict[str, set[int] | None] = {}
    for machine in machines:
        files = split.get(machine["name"]) or []
        if not files:
            continue
        slice_plan = [(rel, by_rel[rel]) for rel in files]
        if machine["transport"] == "docker_context":
            result = _measure_slice_on_dell(machine.get("context", "dell"),
                                             slice_plan)
            sys.stdout.write(
                f"[COVERAGE SPLIT: {machine['name']} measured {files}]\n"
            )
            if result is None:  # whole slice untrusted → re-measure locally
                sys.stdout.write(
                    f"[COVERAGE SPLIT: {machine['name']} unreachable/unverified — "
                    f"re-running {files} locally]\n"
                )
                result = _measure_local(slice_plan)
        else:
            sys.stdout.write(
                f"[COVERAGE SPLIT: {machine['name']} (local) measured {files}]\n"
            )
            result = _measure_local(slice_plan)
        merged.update(result)
    return merged


def _measure_missing_map(production: list[str]
                         ) -> dict[str, set[int] | None]:
    """Return {staged-path -> missing-line-set-or-None} for files with a floor.

    Chooses the two-machine split when XF_COVERAGE_SPLIT=1, else today's local
    run. Keyed by the ORIGINAL staged path so the floor evaluator can look each
    file up directly.
    """
    plan: list[tuple[str, list[str]]] = []  # (rel_to_backend, tests)
    rel_to_path: dict[str, str] = {}
    for path in production:
        rel = path[len("backend/"):]
        plan.append((rel, _test_paths_for(path)))
        rel_to_path[rel] = path
    if not plan:
        return {}
    if os.environ.get("XF_COVERAGE_SPLIT", "").strip() == "1":
        by_rel = _measure_split(plan)
    else:
        by_rel = _measure_local(plan)
    return {rel_to_path[rel]: missing for rel, missing in by_rel.items()}


def main() -> int:
    staged = _staged_files()
    production = [p for p in staged if _is_production_py(p)]
    if not production:
        return 0
    resolver = _load_resolver()

    floored = [p for p in production
               if (resolver.tier_line_floor(p) or 0) > 0]
    missing_map = _measure_missing_map(floored)

    failures: list[str] = []
    for path in production:
        floor = resolver.tier_line_floor(path)
        if floor is None or floor <= 0:
            continue  # smoke tier / no measurable floor — allowed
        changed = _changed_lines(path)
        tests = _test_paths_for(path)
        missing = missing_map.get(path)
        if missing is None:
            # No tests, or unmeasurable. Only a problem if there ARE changed
            # executable lines that therefore cannot be shown as covered.
            if tests:
                failures.append(f"  {path}: coverage could not be measured")
            else:
                failures.append(
                    f"  {path}: changed code but no test found "
                    f"(add tests_{Path(path).stem}.py or stage a test in the app)"
                )
            continue
        if changed is None:
            # Brand-new file: every missing line is uncovered new code.
            if missing:
                shown = ", ".join(str(n) for n in sorted(missing)[:15])
                failures.append(f"  {path}: new file has uncovered lines {shown}")
            continue
        uncovered_changed = sorted(changed & missing)
        if uncovered_changed:
            shown = ", ".join(str(n) for n in uncovered_changed[:15])
            failures.append(f"  {path}: changed lines not covered: {shown}")

    if failures:
        return _fail("\n".join(failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
