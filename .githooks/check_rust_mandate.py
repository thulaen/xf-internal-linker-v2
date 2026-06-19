from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from _hook_helpers import staged_paths


@dataclass(frozen=True)
class RustWorkspace:
    """One Rust workspace the mandate gate guards.

    prefix              repo-relative path prefix; a staged file under it trips
                        the gate for this workspace.
    container_workspace absolute path of the workspace inside the
                        compiled-tools container (where cargo runs).
    rel_workspace       repo-relative path of the workspace on the host (the
                        directory that holds the top-level Cargo.toml).
    mutants_package     the `-p <name>` package cargo-mutants exercises.
    mutants_test_args   extra args passed to the test runner cargo-mutants
                        invokes (after `--`). speccheck routes mutation tests
                        to its `catalog` integration test; the rust/ kernels
                        use plain inline unit tests, so they pass no `--test`
                        selector (an empty tuple runs the default test set).
    """

    prefix: str
    container_workspace: str
    rel_workspace: str
    mutants_package: str
    mutants_test_args: tuple[str, ...]


# Adding a future Rust workspace is a one-line append here — the gate logic
# below iterates this list, so there is no hardcoded single path anymore.
RUST_WORKSPACES: tuple[RustWorkspace, ...] = (
    RustWorkspace(
        prefix="services/speccheck/",
        container_workspace="/repo/services/speccheck",
        rel_workspace="services/speccheck",
        mutants_package="speccheck-detectors",
        mutants_test_args=("--test", "catalog"),
    ),
    RustWorkspace(
        prefix="rust/",
        container_workspace="/repo/rust",
        rel_workspace="rust",
        mutants_package="l2norm",
        mutants_test_args=(),
    ),
)

# The coverage ratchet script (scripts/run-rust-coverage.sh) replaces the old
# inline `cargo +nightly llvm-cov --fail-under-lines 100` cliff. It measures
# stable-toolchain line coverage and enforces a per-workspace floor that can
# only rise toward the 95% target, so a workspace currently at ~72% (the
# rust/ kernels, whose #[pyfunction] wrappers cargo test cannot reach) is
# committable while ratcheting up. See docs/PYTHON-RUST-MIGRATION-PLAN.md E8.
COVERAGE_RATCHET_SCRIPT = "/repo/scripts/run-rust-coverage.sh"

# Steps whose tool may be genuinely absent from the image. A missing binary
# here degrades to a Rule-F WARNING + continue (defense in depth) instead of a
# crash; the primary fix is installing the tool in tools/mutation/Dockerfile.
GRACEFUL_STEPS = frozenset({"audit", "deny"})

# Anchored substrings that mark "the tool is not installed" rather than "the
# check found a real problem". A missing-tool outcome is the ONLY thing the
# graceful path swallows, so the markers must be precise: a bare "no such file
# or directory" or "no such command" can appear inside a REAL audit/deny finding,
# and matching them anywhere would swallow a genuine security/license failure
# (a bypass). Two reliable shapes occur:
#   - the shell cannot find the binary:  `bash: cargo-audit: command not found`
#   - cargo cannot find the subcommand:  `error: no such command: 'audit'`
# (cargo exits 101 for the second, not 127, so the anchored message is the
# reliable signal — we must not treat every cargo 101 as "missing tool".)
_MISSING_TOOL_MARKERS = (
    "command not found",
    "error: no such command:",
)

# ── Dell helper wiring ────────────────────────────────────────────────────────
# MSI (Windows) carries build/test weight 0.0 under the fail-closed routing in
# config/mutation-routing.json, and its local `compiled-tools` image was removed
# to reclaim disk. ALL Rust compile/test/clippy/mutation/coverage therefore runs
# on the Dell helper, mirroring scripts/dell-rust.sh and
# scripts/run-dell-quality-shard.sh: the source is synced into the
# `xf_dell_compiled_repo` volume, then cargo runs inside Dell's
# xf-linker-compiled-tools image with the shared artifact + cache volumes mounted.
DELL_CONTEXT = "dell"
DELL_IMAGE = "xf-linker-compiled-mutation-tools:latest"
DELL_REPO_VOLUME = "xf_dell_compiled_repo"
DELL_CACHE_VOLUME = "xf_dell_compiled_cache"
DELL_ARTIFACTS_VOLUME = "compiled_artifacts"

# Source trees synced into the Dell volume before any cargo step runs. Both Rust
# workspaces (services/speccheck + rust/) live under these roots; .githooks and
# scripts/ carry the coverage-ratchet script the coverage step shells.
_DELL_SYNC_ROOTS = ("services", "rust", "scripts", ".githooks")
_DELL_SYNC_EXCLUDE_PATHS = (
    "services/speccheck/target",
    "rust/target",
    "rust/mutants.out",
    "rust/mutants.out.old",
)


def _gate_steps(ws: RustWorkspace) -> tuple[tuple[str, str], ...]:
    """Per-workspace (step name, cargo/shell command) pairs."""
    return (
        ("fmt", "cargo fmt --check"),
        (
            "clippy",
            "cargo clippy --workspace --all-targets -- "
            "-D warnings -W clippy::all -W clippy::pedantic -W clippy::nursery -W clippy::cargo",
        ),
        ("tests", "cargo test --workspace --all-targets"),
        ("doc_tests", "cargo test --workspace --doc"),
        # Stable-toolchain coverage via the ratchet, scoped to this workspace.
        (
            "coverage",
            f"RUST_WORKSPACES={ws.container_workspace} bash {COVERAGE_RATCHET_SCRIPT}",
        ),
        (
            "mutants",
            _mutants_command(ws),
        ),
        ("audit", "cargo audit -D warnings"),
        ("deny", "cargo deny check"),
    )


def _mutants_command(ws: RustWorkspace) -> str:
    """Bazel-owned Rust mutation command for one workspace."""
    return "python scripts/bazel_default.py run //tools/quality:mutation"


def _staged_rust_workspaces(root: Path) -> list[RustWorkspace]:
    """Return every workspace whose prefix matches a staged path."""
    staged = staged_paths(root)
    return [ws for ws in RUST_WORKSPACES if any(p.startswith(ws.prefix) for p in staged)]


def main(repo_root: Path | None = None) -> int:
    root = repo_root or Path(__file__).resolve().parents[1]
    workspaces = _staged_rust_workspaces(root)
    if not workspaces:
        return 0

    summaries: list[str] = []
    for ws in workspaces:
        if not (root / ws.rel_workspace).exists():
            return _fail(
                "workspace missing",
                f"create {ws.rel_workspace} before staging Rust files under {ws.prefix}",
            )
        result_or_code = _run_workspace_gate(root, ws)
        if isinstance(result_or_code, int):
            return result_or_code
        summaries.append(result_or_code)

    for line in summaries:
        print(line)
    return 0


def _run_workspace_gate(root: Path, ws: RustWorkspace) -> int | str:
    """Run every gate step for one workspace.

    Returns the exit code (2) on a hard failure, or the summary string on
    success. Missing graceful-step tools degrade to a warning + continue.
    """
    reachability = subprocess.run(
        _dell_docker_command("version"),
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    if reachability.returncode != 0:
        return _fail(
            "Dell unavailable",
            "WHY: Rust checks must run on Dell because MSI has no local Docker "
            "toolchain.\n"
            "UNBLOCK: restore SSH access to Dell Docker, then rerun the commit.\n"
            f"{(reachability.stdout + reachability.stderr).strip()}",
        )
    sync_result = _sync_dell_source(root)
    if sync_result.returncode != 0:
        return _fail("Dell source sync", _process_output(sync_result))
    statuses: dict[str, str] = {}
    for name, cargo_command in _gate_steps(ws):
        result = subprocess.run(
            _docker_command(ws.container_workspace, cargo_command),
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=900,
        )
        if result.returncode == 0:
            statuses[name] = "pass"
            continue
        combined = (result.stdout + result.stderr).strip()
        if name in GRACEFUL_STEPS and _looks_like_missing_tool(result.returncode, combined):
            _warn_missing_tool(ws, name, combined)
            statuses[name] = "skipped"
            continue
        return _fail(f"{ws.rel_workspace}:{name}", combined)
    return _summary_line(ws, statuses)


def _sync_dell_source(root: Path) -> subprocess.CompletedProcess:
    """Copy the current Rust gate source roots into the Dell repo volume."""
    existing_roots = [path for path in _DELL_SYNC_ROOTS if (root / path).exists()]
    if not existing_roots:
        return subprocess.CompletedProcess(args=["tar"], returncode=1, stdout="", stderr="no roots")

    tmp_dir = root / ".tmp"
    tmp_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="rust-mandate-", suffix=".tar", dir=tmp_dir, delete=False
    ) as tmp_file:
        tar_path = Path(tmp_file.name)
    try:
        with tarfile.open(tar_path, "w") as archive:
            for source_root in existing_roots:
                archive.add(root / source_root, arcname=source_root, filter=_filter_tar_member)
        return _upload_dell_source(root, tar_path)
    finally:
        tar_path.unlink(missing_ok=True)


def _upload_dell_source(root: Path, tar_path: Path) -> subprocess.CompletedProcess:
    """Upload one prepared source archive to Dell's Rust gate volume."""
    extract_command = (
        "rm -rf /repo/services /repo/rust /repo/scripts /repo/.githooks "
        "&& tar -xf - -C /repo"
    )
    docker_cmd = _dell_docker_command(
        "run",
        "--rm",
        "-i",
        "-v",
        f"{DELL_REPO_VOLUME}:/repo",
        "alpine:latest",
        "sh",
        "-c",
        extract_command,
    )
    with tar_path.open("rb") as source_archive:
        return subprocess.run(
            docker_cmd,
            cwd=root,
            stdin=source_archive,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=300,
        )


def _filter_tar_member(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Drop generated Rust outputs from the source archive sent to Dell."""
    name = member.name.replace("\\", "/")
    for excluded in _DELL_SYNC_EXCLUDE_PATHS:
        if name == excluded or name.startswith(f"{excluded}/"):
            return None
    return member


def _docker_command(container_workspace: str, cargo_command: str) -> list[str]:
    return _dell_docker_command(
        "run",
        "--rm",
        "-v",
        f"{DELL_REPO_VOLUME}:/repo",
        "-v",
        f"{DELL_CACHE_VOLUME}:/cargo-cache",
        "-v",
        f"{DELL_ARTIFACTS_VOLUME}:/opt/xf/compiled",
        "-e",
        "CARGO_TERM_COLOR=never",
        "-w",
        container_workspace,
        DELL_IMAGE,
        "bash",
        "-lc",
        cargo_command,
    )


def _dell_docker_command(*docker_args: str) -> list[str]:
    return [
        sys.executable,
        "scripts/remote_docker.py",
        "--host",
        DELL_CONTEXT,
        "--",
        *docker_args,
    ]


def _looks_like_missing_tool(returncode: int, output: str) -> bool:
    """True when the failure is 'binary not installed', not a real finding."""
    lowered = output.lower()
    if any(marker in lowered for marker in _MISSING_TOOL_MARKERS):
        return True
    # `bash -lc "cargo audit ..."` returns 127 when the subcommand is absent.
    return returncode == 127


def _process_output(result: subprocess.CompletedProcess) -> str:
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    return (stdout + stderr).strip()


def _warn_missing_tool(ws: RustWorkspace, step: str, detail: str) -> None:
    """Rule-F plain-English warning that a security tool is absent."""
    print(f"WARNING check-rust-mandate: {step} skipped for {ws.rel_workspace}", file=sys.stderr)
    print(
        f"WHY: the '{step}' tool is not installed in the compiled-tools image, "
        "so this security/license check could not run. The build is NOT blocked, "
        "but the check did not actually run.",
        file=sys.stderr,
    )
    print(
        "UNBLOCK: install the tool in tools/mutation/Dockerfile "
        "(`cargo install cargo-audit cargo-deny`) and rebuild the compiled-tools image "
        "so the check runs for real.",
        file=sys.stderr,
    )
    if detail:
        print(f"DETAIL: {detail}", file=sys.stderr)


def _summary_line(ws: RustWorkspace, statuses: dict[str, str]) -> str:
    def mark(step: str) -> str:
        return statuses.get(step, "fail")

    return (
        f"[RUST GATE: workspace={ws.rel_workspace} "
        f"fmt={mark('fmt')} "
        f"clippy={mark('clippy')} "
        f"tests={mark('tests')} "
        f"doc_tests={mark('doc_tests')} "
        f"coverage={mark('coverage')}(ratchet) "
        f"mutants={mark('mutants')} "
        f"audit={mark('audit')} "
        f"deny={mark('deny')}]"
    )


def _fail(step: str, detail: str) -> int:
    print(f"FAIL check-rust-mandate: {step}", file=sys.stderr)
    print(f"WHY: {detail or 'the Rust gate returned a non-zero result'}", file=sys.stderr)
    print("UNBLOCK: run the Docker-managed Rust gate and fix the named failure.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
