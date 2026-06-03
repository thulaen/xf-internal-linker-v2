#!/usr/bin/env python3
"""Turbo mutation coordinator — weighted N-way parallel split.

Each language runs its own tool independently.  Python and TypeScript always
run locally on Windows (their containers only live there).  C++, Go, Rust, and
Haskell fan their targets out across every REACHABLE machine by weight: the
Dell helper takes up to 60 % (a ceiling, not an exact target), Windows 30 %,
and the Mint helper 10 %.  Any machine that is powered off is dropped before
work is assigned and its share is redistributed to the machines that answer,
so a switched-off box never blocks the run.  Surviving mutants are filed as
AutoIssues via ``manage.py file_mutation_survivors``.

Usage::

    python scripts/turbo_mutation.py --language python [--dry-run] [--cores N]
    python scripts/turbo_mutation.py --language cpp    [--dry-run] [--cores N]

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

_ALL_LANGUAGES = ("python", "cpp", "go", "typescript", "rust", "haskell")


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
# 17 existing tests) resolve to the one canonical copy of the weighting math.
_machines_from_config = _routing._machines_from_config
_local_machine = _routing._local_machine
_renormalise_with_ceilings = _routing._renormalise_with_ceilings
_select_machines = _routing._select_machines
_probe_reachable = _routing._probe_reachable
_partition_weighted = _routing._partition_weighted
_dispatch_to_machines = _routing._dispatch_to_machines

# Probe budgets — re-exported for any caller that referenced them here.
_PROBE_DOCKER_TIMEOUT = _routing._PROBE_DOCKER_TIMEOUT
_PROBE_SSH_TIMEOUT = _routing._PROBE_SSH_TIMEOUT


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


# ── weighted machine selection (pure, fail-open) ──────────────────────────────
# The selection + partition math lives in scripts/machine_routing.py and is
# re-exported at the top of this module so it is single-sourced with the
# per-commit scoped-mutation gate. Only the turbo-specific wrapper stays here.


def _machines_for_language(
    cfg: dict, split_enabled: bool, probe: Callable[[dict], bool] | None = None
) -> list[dict]:
    """Reachable machine list for a language; split:false stays Windows-only."""
    if not split_enabled:
        return [{"name": "windows", "transport": "docker_local",
                 "weight": 1.0, "max_weight": 1.0, "share": 1.0}]
    return _select_machines(cfg, probe)


def _sync_source_to_dell_for_turbo(machine: dict) -> str | None:
    """Tar the working tree to the Dell before an ssh run (reuses the gate helper)."""
    gate = _load_gate_module()
    host = machine.get("ssh_host", machine["name"])
    repo = os.environ.get("DELL_REPO_PATH", r"C:\Users\PC\xf-internal-linker-v2")
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    return gate._sync_source_to_dell(host, repo, env)


def _load_gate_module():
    """Import the scoped-mutation hook so the SSH helpers are single-sourced."""
    path = REPO_ROOT / ".githooks" / "check-scoped-mutation.py"
    spec = importlib.util.spec_from_file_location("check_scoped_mutation", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ssh_docker_command(machine: dict, container: str, cmd: str) -> list[str]:
    """Build the ssh argv that runs `cmd` in an ephemeral container on the Dell."""
    host = machine.get("ssh_host", machine["name"])
    repo = os.environ.get("DELL_REPO_PATH", r"C:\Users\PC\xf-internal-linker-v2")
    docker_cfg = os.environ.get("DELL_DOCKER_CONFIG", r"C:\Users\PC\.docker-mut")
    remote = (
        f"set DOCKER_CONFIG={docker_cfg}&& cd {repo} && "
        f"docker compose run --rm --no-deps -T {container} bash -lc {json.dumps(cmd)}"
    )
    return ["ssh", "-o", "BatchMode=yes", host, remote]


def _run_in_container(
    transport: str,
    container: str,
    cmd: str,
    *,
    context: str | None = None,
    ssh_host: str | None = None,
    timeout: int = 600,
) -> tuple[int, str]:
    """Run cmd in a container via one of three transports.  Returns (rc, output).

    `transport` is "docker_local" / "local" (Windows), "docker_context" plus a
    context name (Mint), or "ssh" plus an ssh_host (Dell). The legacy callers
    that pass a context string ("local" / "mint") as the first argument keep
    working: a non-transport value is treated as a docker context.
    """
    if transport in ("docker_local", "local"):
        docker_cmd = ["docker", "compose", "exec", "-T", container, "bash", "-lc", cmd]
    elif transport == "ssh":
        machine = {"name": ssh_host or "dell", "ssh_host": ssh_host or "dell"}
        sync_problem = _sync_source_to_dell_for_turbo(machine)
        if sync_problem is not None:
            return 1, f"[turbo] ssh sync failed: {sync_problem}\n"
        docker_cmd = _ssh_docker_command(machine, container, cmd)
    else:
        ctx = context if transport == "docker_context" else transport
        docker_cmd = [
            "docker", "--context", ctx,
            "compose", "exec", "-T", container, "bash", "-lc", cmd,
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
        context=machine.get("context"), ssh_host=machine.get("ssh_host"),
        timeout=timeout,
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

def _run_python(cfg: dict, cores_local: int, dry_run: bool) -> str:
    """mutmut on all backend/apps Python files — local only, all cores."""
    paths = os.environ.get("XF_MUTMUT_PATHS", "apps/")
    report_host = TMP_DIR / "mutmut-survivors.json"
    TMP_DIR.mkdir(exist_ok=True)

    mutmut_cmd = (
        f"cd /repo/backend && "
        f"workdir=/tmp/xf-mutmut-turbo; "
        f"rm -rf \"$workdir\"; "
        f"mkdir -p \"$workdir\"; "
        f"ln -s /repo/backend/apps \"$workdir/apps\"; "
        f"ln -s /repo/backend/config \"$workdir/config\"; "
        f"ln -s /repo/backend/pytest.ini \"$workdir/pytest.ini\"; "
        f"ln -s /repo/backend/conftest.py \"$workdir/conftest.py\"; "
        f"python - \"$workdir\" {json.dumps(paths)} <<'PY'\n"
        f"from pathlib import Path\n"
        f"import sys\n"
        f"import os\n"
        f"import json\n"
        f"workdir = Path(sys.argv[1])\n"
        f"paths = [p for p in sys.argv[2].split() if p]\n"
        f"tests = {json.dumps(os.environ.get('XF_MUTMUT_TESTS', 'apps'))}\n"
        f"workdir.joinpath('pyproject.toml').write_text(\n"
        f"    '[tool.mutmut]\\n'\n"
        f"    f'paths_to_mutate = \"{{paths[0]}}\"\\n'\n"
        f"    'also_copy = [\"apps\", \"config\", \"pytest.ini\", \"conftest.py\"]\\n'\n"
        f"    f'runner = \"env DJANGO_SETTINGS_MODULE=config.settings.development python -m pytest -x -q --reuse-db {{tests}}\"\\n'\n"
        f"    'tests_dir = \"apps/\"\\n',\n"
        f"    encoding='utf-8',\n"
        f")\n"
        f"PY\n"
        f"cd \"$workdir\"; "
        f"find {paths} -name '*.pyc' -delete 2>/dev/null; "
        f"python -m mutmut run --max-children {cores_local} || true; "
        f"python -m mutmut export-cicd-stats > /tmp/mutmut-survivors.json 2>/dev/null || true; "
        f"cat /tmp/mutmut-survivors.json"
    )
    rc, out = _run_in_container("local", "backend", mutmut_cmd, timeout=540)
    print(out, end="")
    _write_json_blob(out, report_host)
    return _file_survivors("mutmut", report_host, dry_run)


def _fanout(
    machines: list[dict], items: list, body: Callable[[dict, list], None]
) -> None:
    """Partition `items` by weight and run `body(machine, slice)` per machine."""
    plan = _partition_weighted(items, machines)
    _dispatch_to_machines(machines, plan, body)


def _run_cpp(cfg: dict, machines: list[dict], machine_cores: dict, dry_run: bool) -> str:
    """Mull on the C++ binaries — weighted across every reachable machine."""
    binaries: list[str] = cfg["languages"]["cpp"]["binaries"]
    report_dir_host = TMP_DIR / "mull-reports"
    report_dir_host.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    lock = threading.Lock()

    def body(machine: dict, bins: list[str]) -> None:
        for binary in bins:
            cmd = (
                f"mull-runner-19 -reporters Elements -report-dir /tmp/mull-reports "
                f"/repo/backend/build/{binary} -timeout 60 || true"
            )
            rc, out = _run_on_machine(machine, "compiled-tools", cmd, timeout=180)
            with lock:
                outputs.append(f"[turbo cpp {machine['name']}:{binary}] rc={rc}\n{out}")

    _fanout(machines, binaries, body)
    result = "\n".join(outputs)
    print(result)

    for machine in machines:
        rc, out = _run_on_machine(
            machine, "compiled-tools",
            "cat /tmp/mull-reports/*.json 2>/dev/null || true", timeout=30,
        )
        if out.strip():
            try:
                data = json.loads(out.strip())
                (report_dir_host / f"mull-{machine['name']}.json").write_text(
                    json.dumps(data), encoding="utf-8")
            except json.JSONDecodeError:
                pass

    filing_out = ""
    for report_file in sorted(report_dir_host.glob("mull-*.json")):
        filing_out += _file_survivors("mull", report_file, dry_run)
    return result + filing_out


def _run_go(cfg: dict, machines: list[dict], machine_cores: dict, dry_run: bool) -> str:
    """go-mutesting on services/ — weighted across every reachable machine."""
    workspace = cfg["languages"]["go"]["workspace"]
    report_host = TMP_DIR / "go-mutesting-report.json"
    TMP_DIR.mkdir(exist_ok=True)
    outputs: list[str] = []
    lock = threading.Lock()

    def body(machine: dict, _slice: list) -> None:
        name = machine["name"]
        gomax = _jobs_for(machine_cores.get(name, 2), machine["share"])
        cmd = (
            f"cd {workspace} && GOMAXPROCS={gomax} "
            f"go-mutesting ./... 2>&1 | tee /tmp/go-mut-{name}.txt || true; "
            f"python3 -c \""
            f"import re, json; "
            f"lines=open('/tmp/go-mut-{name}.txt').read(); "
            f"survivors=[{{'file':m.group(1),'line':int(m.group(2)),'mutator':m.group(3),'replacement':''}} "
            f"for m in re.finditer(r'PASS.*?([^\\s]+\\.go):(\\d+).*?\\((.+?)\\)', lines)]; "
            f"json.dump({{'mutators': [{{'file':s['file'],'line':s['line'],'type':s['mutator'],'result':{{'passed':True}}}} for s in survivors]}}, open('/tmp/go-mut-report-{name}.json','w'))\""
        )
        rc, out = _run_on_machine(machine, "compiled-tools", cmd, timeout=480)
        with lock:
            outputs.append(f"[turbo go {name}] rc={rc}\n{out}")

    # go-mutesting walks the whole workspace; the partition is by machine, so
    # every reachable machine is given a 1-item placeholder slice to run once.
    _fanout(machines, list(range(len(machines))), body)
    result = "\n".join(outputs)
    print(result)

    merged: list[dict] = []
    for machine in machines:
        rc2, raw = _run_on_machine(
            machine, "compiled-tools",
            f"cat /tmp/go-mut-report-{machine['name']}.json 2>/dev/null || echo '{{}}'",
            timeout=20,
        )
        try:
            merged.extend((json.loads(raw.strip() or "{}").get("mutators")) or [])
        except json.JSONDecodeError:
            pass

    if merged:
        report_host.write_text(json.dumps({"mutators": merged}), encoding="utf-8")
    return result + _file_survivors("go-mutesting", report_host, dry_run)


def _run_rust(cfg: dict, machines: list[dict], machine_cores: dict, dry_run: bool) -> str:
    """cargo-mutants on speccheck — --jobs derived from each machine's weight."""
    workspace = cfg["languages"]["rust"]["workspace"]
    TMP_DIR.mkdir(exist_ok=True)
    outputs: list[str] = []
    lock = threading.Lock()

    def body(machine: dict, _slice: list) -> None:
        name = machine["name"]
        jobs = _jobs_for(machine_cores.get(name, 2), machine["share"])
        cmd = (
            f"cd {workspace} && cargo mutants --jobs {jobs} "
            f"--output /tmp/mutants-{name}.out || true; "
            f"cat /tmp/mutants-{name}.out/outcomes.json 2>/dev/null || echo '{{}}'"
        )
        rc, out = _run_on_machine(machine, "compiled-tools", cmd, timeout=480)
        with lock:
            outputs.append(f"[turbo rust {name}] rc={rc}\n{out}")
        try:
            blob = json.loads(out[out.rindex("{"):])
            (TMP_DIR / f"rust-outcomes-{name}.json").write_text(
                json.dumps(blob), encoding="utf-8")
        except (ValueError, json.JSONDecodeError):
            pass

    _fanout(machines, list(range(len(machines))), body)
    result = "\n".join(outputs)
    print(result)

    filing_out = ""
    for machine in machines:
        report_file = TMP_DIR / f"rust-outcomes-{machine['name']}.json"
        filing_out += _file_survivors("cargo-mutants", report_file, dry_run)
    return result + filing_out


def _run_haskell(cfg: dict, machines: list[dict], machine_cores: dict, dry_run: bool) -> str:
    """mucheck — run on every reachable machine; parse stdout to JSON and file."""
    workspace = cfg["languages"]["haskell"]["workspace"]
    TMP_DIR.mkdir(exist_ok=True)
    outputs: list[str] = []
    lock = threading.Lock()

    def body(machine: dict, _slice: list) -> None:
        name = machine["name"]
        cmd = (
            f"cd {workspace} && "
            f"mucheck --timeout 60 --module-dir . --test-suite all 2>&1 | tee /tmp/mucheck-{name}.txt || true; "
            f"python3 -c \""
            f"import re, json; "
            f"txt=open('/tmp/mucheck-{name}.txt').read(); "
            f"survivors=[{{'file':m.group(1),'line':int(m.group(2)),'mutator':m.group(3),'replacement':''}} "
            f"for m in re.finditer(r'Mutant.*?\\\"([^:]+):(\\d+).*?survived.*?\\((.+?)\\)', txt, re.I|re.S)]; "
            f"json.dump({{'survivors':survivors}}, open('/tmp/mucheck-report-{name}.json','w'))\""
        )
        rc, out = _run_on_machine(machine, "compiled-tools", cmd, timeout=480)
        with lock:
            outputs.append(f"[turbo haskell {name}] rc={rc}\n{out}")

    _fanout(machines, list(range(len(machines))), body)
    result = "\n".join(outputs)
    print(result)

    filing_out = ""
    for machine in machines:
        rc2, raw = _run_on_machine(
            machine, "compiled-tools",
            f"cat /tmp/mucheck-report-{machine['name']}.json 2>/dev/null || echo '{{\"survivors\":[]}}'",
            timeout=20,
        )
        report_host = TMP_DIR / f"mucheck-report-{machine['name']}.json"
        try:
            report_host.write_text(
                json.dumps(json.loads(raw.strip() or '{"survivors":[]}')), encoding="utf-8")
        except json.JSONDecodeError:
            pass
        filing_out += _file_survivors("mucheck", report_host, dry_run)
    return result + filing_out


def _run_typescript(cfg: dict, cores_local: int, dry_run: bool) -> str:
    """Stryker on Angular frontend — local only."""
    workspace = cfg["languages"]["typescript"]["workspace"]
    report_container = cfg["languages"]["typescript"]["report_container"]
    report_host = REPO_ROOT / cfg["languages"]["typescript"]["report_host"]

    cmd = (
        f"cd {workspace} && "
        f"npx stryker run --concurrency {cores_local} 2>&1 || true"
    )
    rc, out = _run_in_container("local", "xf_linker_compiled_tools", cmd, timeout=540)
    print(out)
    return _file_survivors("stryker", report_host, dry_run)


# ── entry point ───────────────────────────────────────────────────────────────

def _machine_cores(machine: dict, override: int) -> int:
    """CPU count for a machine: --cores override, else probe its transport."""
    if override:
        return override
    transport = machine["transport"]
    if transport in ("docker_local", "local"):
        return _docker_cores("local")
    if transport == "docker_context":
        return _docker_cores(machine["context"])
    return 20  # ssh/Dell: 20-core box; remote core probe over SSH is not worth it


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Turbo weighted N-way mutation coordinator "
        "(Dell up to 60% / Windows 30% / Mint 10%; offline machines redistribute).")
    parser.add_argument("--language", required=True, choices=list(_ALL_LANGUAGES),
                        help="Which language to mutate.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run mutations but do not write AutoIssues.")
    parser.add_argument("--cores", type=int, default=0,
                        help="Override detected CPU count (0 = auto).")
    return parser


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    args = _build_arg_parser().parse_args()

    cfg = _load_config()
    TMP_DIR.mkdir(exist_ok=True)

    split_enabled = cfg["languages"][args.language].get("split", False)
    machines = _machines_for_language(cfg, split_enabled)
    cores = {m["name"]: _machine_cores(m, args.cores) for m in machines}

    plan_desc = ", ".join(f"{m['name']}={m['share']:.0%}" for m in machines)
    print(f"[turbo] language={args.language} split={split_enabled} "
          f"reachable=[{plan_desc}] dry_run={args.dry_run}")

    local_cores = cores.get("windows") or next(iter(cores.values()), 2)
    dispatch = {
        "python":     lambda: _run_python(cfg, local_cores, args.dry_run),
        "cpp":        lambda: _run_cpp(cfg, machines, cores, args.dry_run),
        "go":         lambda: _run_go(cfg, machines, cores, args.dry_run),
        "rust":       lambda: _run_rust(cfg, machines, cores, args.dry_run),
        "haskell":    lambda: _run_haskell(cfg, machines, cores, args.dry_run),
        "typescript": lambda: _run_typescript(cfg, local_cores, args.dry_run),
    }

    filing_output = dispatch[args.language]()
    print(filing_output)

    gate = cfg.get("kill_rate_gates", {}).get(args.language, 0)
    print(f"[turbo] done — kill-rate gate for {args.language}: {gate:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
