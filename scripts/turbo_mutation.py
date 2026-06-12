#!/usr/bin/env python3
"""Turbo mutation coordinator — Dell docker-context only, fail-closed.

Each language runs its own tool independently, and EVERY run goes through the
``docker_context`` transport (the Dell docker connection).  There is no ssh
path and no local Windows execution: if the Dell context is unreachable the
run hard-fails with a plain-English "fix Dell" message instead of falling back.
Surviving mutants are filed as AutoIssues via
``manage.py file_mutation_survivors``.

Usage::

    python scripts/turbo_mutation.py --language python [--dry-run] [--cores N]
    python scripts/turbo_mutation.py --language rust   [--dry-run] [--cores N]

``--cores`` overrides the auto-detected CPU count on each machine.
Set ``XF_TURBO_MUTATION=1`` to activate turbo mode from existing quality scripts.
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
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "mutation-routing.json"
TMP_DIR = REPO_ROOT / ".tmp"

_ALL_LANGUAGES = ("python", "typescript", "rust")


def _load_machine_routing():
    """Import the shared routing math by absolute path (single-sourced; DRY)."""
    path = REPO_ROOT / "scripts" / "machine_routing.py"
    spec = importlib.util.spec_from_file_location("machine_routing", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_routing = _load_machine_routing()

# Re-export the shared routing functions so this module's public names (and its
# existing tests) resolve to the one canonical copy of the weighting math.
_machines_from_config = _routing._machines_from_config
_renormalise_with_ceilings = _routing._renormalise_with_ceilings
_select_machines = _routing._select_machines
_probe_reachable = _routing._probe_reachable
_partition_weighted = _routing._partition_weighted
_dispatch_to_machines = _routing._dispatch_to_machines

# Probe budget — re-exported for any caller that referenced it here.
_PROBE_DOCKER_TIMEOUT = _routing._PROBE_DOCKER_TIMEOUT


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _docker_cores(context: str = "local") -> int:
    """Return the number of CPUs available inside Docker on the given context."""
    cmd = ["docker", "info", "--format", "{{.NCPU}}"]
    if context != "local":
        cmd = ["docker", "--context", context] + cmd[1:]
    try:
        out = subprocess.check_output(cmd, timeout=15, text=True, encoding="utf-8", stderr=subprocess.DEVNULL)
        return max(1, int(out.strip()))
    except Exception:
        return 2  # safe fallback


def _jobs_for(cores: int, share: float) -> int:
    """CPU job budget for one machine = round(cores * share), never below 1."""
    return max(1, round(cores * share))


# ── weighted machine selection ────────────────────────────────────────────────
# The selection + partition math lives in scripts/machine_routing.py and is
# re-exported at the top of this module so it is single-sourced with the other
# quality runners. main() calls _select_machines(cfg) directly.


def _run_in_container(
    transport: str,
    container: str,
    cmd: str,
    *,
    context: str | None = None,
    timeout: int = 600,
) -> tuple[int, str]:
    """Run cmd in a container on a docker context.  Returns (rc, output).

    Only the ``docker_context`` transport is allowed.  Any other transport
    (ssh, docker_local, local, legacy context strings) fails closed with rc 1
    and never spawns a subprocess — mutation work must never run on the local
    Windows box or over ssh.
    """
    if transport != "docker_context":
        return 1, (
            f"transport {transport} is not allowed; all mutation work runs"
            " through the Dell docker context (fail-closed). UNBLOCK: fix the"
            " dell docker context — work never falls back to Windows."
        )
    if not context:
        return 1, (
            "docker_context transport was given no context name (fail-closed)."
            " UNBLOCK: set \"context\": \"dell\" on the machine entry in"
            " config/mutation-routing.json."
        )
    docker_cmd = [
        "docker", "--context", context,
        "run", "--rm",
        "-v", "xf_python_mutation_repo:/repo",
        "-v", "xf_dell_quality_cache:/tmp/xf-test-cache",
        "-v", "frontend_tool_cache:/root/.npm",
        "-w", "/repo",
        "xf-linker-" + container + ":latest",
        "bash", "-lc", cmd,
    ]
    try:
        result = subprocess.run(
            docker_cmd, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, cwd=str(REPO_ROOT), check=False,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 1, f"[turbo] TIMEOUT after {timeout}s\n"
    except Exception as exc:
        return 1, f"[turbo] ERROR: {exc}\n"


def _run_on_machine(
    machine: dict, container: str, cmd: str, *, timeout: int = 600
) -> tuple[int, str]:
    """Dispatch _run_in_container using a machine dict's transport fields."""
    return _run_in_container(
        machine["transport"], container, cmd,
        context=machine.get("context"), timeout=timeout,
    )


def _write_json_blob(raw: str, report_host: Path) -> None:
    """Extract the first JSON object from container output and write it to host."""
    try:
        blob = raw[raw.index("{"):]
        json.loads(blob)  # validate before writing
        report_host.write_text(blob, encoding="utf-8")
    except (ValueError, json.JSONDecodeError):
        pass


def _file_survivors(tool: str, report_host: Path, dry_run: bool = False) -> str:
    """Call manage.py file_mutation_survivors and return its output."""
    if not report_host.is_file():
        return f"[turbo] {tool}: no report at {report_host} — skipping AutoIssue filing\n"
    if dry_run:
        return f"[turbo] {tool}: dry-run — would file from {report_host}\n"
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "file_mutation_survivors",
        "--tool", tool, "--report", f"/repo/{report_host.relative_to(REPO_ROOT)}",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", timeout=120,
            cwd=str(REPO_ROOT), check=False,
        )
        return result.stdout + result.stderr
    except Exception as exc:
        return f"[turbo] {tool}: AutoIssue filing error: {exc}\n"


# ── per-language runners ──────────────────────────────────────────────────────

def _changed_python_mutation_paths() -> list[str]:
    """Backend Python paths to mutate, limited to changed existing files."""
    raw = os.environ.get("XF_MUTMUT_PATHS") or os.environ.get("COMMIT_SCOPE_PATHS")
    if raw:
        candidates = raw.split()
    else:
        mode = os.environ.get("COMMIT_SCOPE_MODE", "staged")
        try:
            out = subprocess.check_output(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "commit_scope.py"),
                    "paths",
                    "--mode",
                    mode,
                ],
                text=True,
                encoding="utf-8",
                cwd=str(REPO_ROOT),
            )
        except Exception:
            out = ""
        candidates = out.splitlines()

    paths: list[str] = []
    for raw_path in candidates:
        path = raw_path.strip().replace("\\", "/")
        if path.startswith("backend/"):
            path = path.removeprefix("backend/")
        if not path.startswith("apps/") or not path.endswith(".py"):
            continue
        if (REPO_ROOT / "backend" / path).is_file():
            paths.append(path)
    return list(dict.fromkeys(paths))


def _run_python(cfg: dict, cores_local: int, dry_run: bool) -> str:
    """mutmut on changed backend/apps Python files only."""
    paths = _changed_python_mutation_paths()
    report_host = TMP_DIR / "mutmut-survivors.json"
    TMP_DIR.mkdir(exist_ok=True)
    if not paths:
        report_host.write_text(
            json.dumps({"skipped": True, "mutants": []}), encoding="utf-8"
        )
        return "[turbo] mutmut: No changed Python mutation targets — skipping.\n"

    mutmut_cmd = (
        f"cd /repo/backend && "
        f"workdir=/tmp/xf-mutmut-turbo; "
        f"rm -rf \"$workdir\"; "
        f"mkdir -p \"$workdir\"; "
        f"ln -s /repo/backend/apps \"$workdir/apps\"; "
        f"ln -s /repo/backend/config \"$workdir/config\"; "
        f"ln -s /repo/backend/pytest.ini \"$workdir/pytest.ini\"; "
        f"ln -s /repo/backend/conftest.py \"$workdir/conftest.py\"; "
        f"python - \"$workdir\" <<'PY'\n"
        f"from pathlib import Path\n"
        f"import sys\n"
        f"import os\n"
        f"import json\n"
        f"workdir = Path(sys.argv[1])\n"
        f"paths = {json.dumps(paths)}\n"
        f"tests = {json.dumps(os.environ.get('XF_MUTMUT_TESTS', 'apps'))}\n"
        f"workdir.joinpath('pyproject.toml').write_text(\n"
        f"    '[tool.mutmut]\\n'\n"
        f"    + 'paths_to_mutate = ' + json.dumps(paths) + '\\n'\n"
        f"    'also_copy = [\"apps\", \"config\", \"pytest.ini\", \"conftest.py\"]\\n'\n"
        f"    f'runner = \"env DJANGO_SETTINGS_MODULE=config.settings.development python -m pytest -x -q --reuse-db {{tests}}\"\\n'\n"
        f"    'tests_dir = \"apps/\"\\n',\n"
        f"    encoding='utf-8',\n"
        f")\n"
        f"PY\n"
        f"cd \"$workdir\"; "
        f"find apps -name '*.pyc' -delete 2>/dev/null; "
        f"ln -sf \"$MUTMUT_CACHE_DIR\" .mutmut-cache; "
        f"python -m mutmut run --max-children {cores_local} || true; "
        f"python -m mutmut export-cicd-stats > /tmp/mutmut-survivors.json 2>/dev/null || true; "
        f"cat /tmp/mutmut-survivors.json"
    )
    mutmut_cmd = f"export MUTMUT_CACHE_DIR=/tmp/xf-test-cache/mutmut; " + mutmut_cmd
    rc, out = _run_in_container("docker_context", "backend-mutation-tools", mutmut_cmd, context="dell", timeout=540)
    print(out, end="")
    _write_json_blob(out, report_host)
    return _file_survivors("mutmut", report_host, dry_run)


def _fanout(
    machines: list[dict], items: list, body: Callable[[dict, list], None]
) -> None:
    """Partition `items` by weight and run `body(machine, slice)` per machine."""
    plan = _partition_weighted(items, machines)
    _dispatch_to_machines(machines, plan, body)


def _rust_workspaces(cfg: dict) -> list[str]:
    """Configured Rust workspaces — the plural `workspaces` list, else legacy."""
    rust = cfg["languages"]["rust"]
    workspaces = rust.get("workspaces")
    if isinstance(workspaces, list) and workspaces:
        return workspaces
    return [rust["workspace"]]


def _rust_slug(workspace: str) -> str:
    """Filesystem-safe slug for a workspace path (for per-workspace filenames)."""
    return workspace.strip("/").replace("/", "-") or "root"


def _rust_mutation_jobs(machine: dict, machine_cores: dict) -> int:
    """Rust cargo-mutants jobs for a machine; Dell defaults to 16."""
    override = os.environ.get("XF_RUST_MUTATION_JOBS")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            return 16
    if machine.get("name") == "dell" or machine.get("context") == "dell":
        return 16
    return _jobs_for(machine_cores.get(machine["name"], 2), machine["share"])


def _run_rust(cfg: dict, machines: list[dict], machine_cores: dict, dry_run: bool) -> str:
    """cargo-mutants over EVERY configured Rust workspace.

    Each (machine, workspace) pair runs cargo-mutants once with a `--jobs`
    budget derived from the machine's weighted share, writing its outcomes to a
    per-workspace report file so survivors from every workspace are filed.
    """
    workspaces = _rust_workspaces(cfg)
    TMP_DIR.mkdir(exist_ok=True)
    outputs: list[str] = []
    lock = threading.Lock()

    def body(machine: dict, _slice: list) -> None:
        name = machine["name"]
        jobs = _rust_mutation_jobs(machine, machine_cores)
        for workspace in workspaces:
            slug = _rust_slug(workspace)
            out_dir = f"/tmp/mutants-{name}-{slug}.out"
            diff_file = os.environ.get("MUTATION_DIFF_FILE", "/repo/.tmp/rust-mutation.diff")
            cmd = (
                f"[ -f {workspace}/Cargo.toml ] || {{ echo '{{}}'; exit 0; }}; "
                f"cd {workspace} && cargo mutants --in-diff {diff_file} --jobs {jobs} "
                f"--output {out_dir} || true; "
                f"cat {out_dir}/outcomes.json 2>/dev/null || echo '{{}}'"
            )
            rc, out = _run_on_machine(machine, "compiled-mutation-tools", cmd, timeout=480)
            with lock:
                outputs.append(f"[turbo rust {name}:{slug}] rc={rc}\n{out}")
            try:
                blob = json.loads(out[out.rindex("{"):])
                (TMP_DIR / f"rust-outcomes-{name}-{slug}.json").write_text(
                    json.dumps(blob), encoding="utf-8")
            except (ValueError, json.JSONDecodeError):
                pass

    _fanout(machines, list(range(len(machines))), body)
    result = "\n".join(outputs)
    print(result)

    filing_out = ""
    for machine in machines:
        for workspace in workspaces:
            slug = _rust_slug(workspace)
            report_file = TMP_DIR / f"rust-outcomes-{machine['name']}-{slug}.json"
            filing_out += _file_survivors("cargo-mutants", report_file, dry_run)
    return result + filing_out


def _run_typescript(cfg: dict, cores_local: int, dry_run: bool) -> str:
    """Stryker on Angular frontend — runs on Dell via docker_context transport."""
    ts_cfg = cfg["languages"]["typescript"]
    workspace = ts_cfg["workspace"]
    container = ts_cfg["container"]  # xf_linker_frontend_mutation_tools
    context = ts_cfg["context"]      # dell
    report_host = REPO_ROOT / ts_cfg["report_host"]

    cores_flag = max(1, cores_local)
    cmd = (
        f"cd {workspace} && "
        f"npx stryker run --incremental --concurrency {cores_flag} 2>&1 || true"
    )
    rc, out = _run_in_container("docker_context", container, cmd,
                                context=context, timeout=540)
    print(out)
    return _file_survivors("stryker", report_host, dry_run)


# ── entry point ───────────────────────────────────────────────────────────────

def _machine_cores(machine: dict, override: int) -> int:
    """CPU count for a machine: --cores override, else probe its docker context."""
    if override:
        return override
    return _docker_cores(machine["context"])


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Turbo mutation coordinator — all work runs on the Dell"
        " docker context (fail-closed; no ssh, no local Windows fallback).")
    parser.add_argument("--language", required=True, choices=list(_ALL_LANGUAGES),
                        help="Which language to mutate.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run mutations but do not write AutoIssues.")
    parser.add_argument("--cores", type=int, default=0,
                        help="Override detected CPU count (0 = auto).")
    return parser


def _kill_rate_from_report(language: str, cfg: dict) -> float | None:
    """Read the survivors report and compute actual kill rate (0.0–1.0).

    Returns None when the report is absent or unreadable (treated as unknown,
    not as a pass — callers should hard-block on None too).
    """
    lang_cfg = cfg["languages"].get(language, {})
    report_key = lang_cfg.get("report_host")
    if not report_key:
        return None
    report_path = REPO_ROOT / report_key
    if not report_path.is_file():
        return None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    # Normalise to a list of mutant dicts regardless of tool format.
    mutants: list[dict] = []
    if isinstance(data, list):
        mutants = data
    elif isinstance(data, dict):
        mutants = (
            data.get("mutants")
            or data.get("survivors")
            or [m for f in data.get("files", {}).values()
                for m in (f.get("mutants") if isinstance(f, dict) else [])]
        ) or []

    if not mutants:
        return None  # no mutants generated — not a pass, treat as unknown

    killed = sum(
        1 for m in mutants
        if isinstance(m, dict)
        and m.get("status") in ("killed", "Killed", "Timeout", "timeout")
    )
    return killed / len(mutants)


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    args = _build_arg_parser().parse_args()

    cfg = _load_config()
    TMP_DIR.mkdir(exist_ok=True)

    machines = _select_machines(cfg)
    cores = {m["name"]: _machine_cores(m, args.cores) for m in machines}

    plan_desc = ", ".join(f"{m['name']}={m['share']:.0%}" for m in machines)
    print(f"[turbo] language={args.language} "
          f"reachable=[{plan_desc}] dry_run={args.dry_run}")

    lead_cores = next(iter(cores.values()), 2)
    dispatch = {
        "python":     lambda: _run_python(cfg, lead_cores, args.dry_run),
        "rust":       lambda: _run_rust(cfg, machines, cores, args.dry_run),
        "typescript": lambda: _run_typescript(cfg, lead_cores, args.dry_run),
    }

    filing_output = dispatch[args.language]()
    print(filing_output)

    # ── kill-rate gate ────────────────────────────────────────────────────────
    # Compare actual kill rate against the configured threshold.  A rate below
    # the floor means too many mutants survived — hard-block the push so the
    # gap cannot be pushed to the remote.  Missing report = hard-block too
    # (mutation failed to run, which is not a pass).
    gate: float = cfg.get("kill_rate_gates", {}).get(args.language, 0.0)
    kill_rate = _kill_rate_from_report(args.language, cfg)

    if kill_rate is None:
        print(
            f"\nFAIL [turbo] {args.language}: mutation report not found or unreadable.",
            file=sys.stderr,
        )
        print(
            f"WHY: turbo_mutation.py could not find a survivors report for"
            f" {args.language} after running the mutation tool.",
            file=sys.stderr,
        )
        print(
            "UNBLOCK: check the mutation tool output above for errors, fix the"
            " container/context issue, then retry the push.",
            file=sys.stderr,
        )
        return 1

    pct = kill_rate * 100.0
    print(f"[turbo] {args.language}: kill_rate={pct:.1f}% gate={gate*100:.0f}%")

    if kill_rate < gate:
        missed = len([1]) * (gate - kill_rate) * 100  # placeholder for count
        print(
            f"\nFAIL [turbo] {args.language}: kill rate {pct:.1f}% is below the"
            f" {gate*100:.0f}% gate — {gate*100 - pct:.1f}pp of mutants survived.",
            file=sys.stderr,
        )
        print(
            f"WHY: {args.language} mutation testing killed only {pct:.1f}% of mutants"
            f" but the repo requires {gate*100:.0f}%. Surviving mutants are code paths"
            " your tests do not actually check.",
            file=sys.stderr,
        )
        print(
            "UNBLOCK: add or strengthen tests until the kill rate meets the gate,"
            " then retry the push. Surviving mutant AutoIssues are in the 'mutation'"
            " picker bucket — resolve them as part of the 30-per-session quota.",
            file=sys.stderr,
        )
        return 1

    print(f"[turbo] {args.language}: kill-rate gate PASSED ({pct:.1f}% >= {gate*100:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
