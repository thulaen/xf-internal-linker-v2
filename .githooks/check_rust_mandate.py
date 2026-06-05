from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _hook_helpers import staged_paths


RUST_PREFIX = "services/speccheck/"
CONTAINER_WORKSPACE = "/repo/services/speccheck"

RUST_GATE_STEPS = (
    ("fmt", "cargo fmt --check"),
    (
        "clippy",
        "cargo clippy --workspace --all-targets -- "
        "-D warnings -W clippy::all -W clippy::pedantic -W clippy::nursery -W clippy::cargo",
    ),
    ("tests", "cargo test --workspace --all-targets"),
    ("doc_tests", "cargo test --workspace --doc"),
    (
        "coverage",
        "cargo +nightly llvm-cov --workspace --branch "
        "--ignore-filename-regex 'crates/cli/src/main.rs' "
        "--fail-under-lines 100",
    ),
    (
        "mutants",
        "cargo mutants -p speccheck-detectors --jobs 4 --timeout 60 "
        "--minimum-test-timeout 30 -- --test catalog",
    ),
    ("audit", "cargo audit -D warnings"),
    ("deny", "cargo deny check"),
)


def main(repo_root: Path | None = None) -> int:
    root = repo_root or Path(__file__).resolve().parents[1]
    if not any(path.startswith(RUST_PREFIX) for path in staged_paths(root)):
        return 0
    workspace = root / "services" / "speccheck"
    if not workspace.exists():
        return _fail("workspace missing", "create services/speccheck before staging Rust files")
    passed: list[str] = []
    for name, cargo_command in RUST_GATE_STEPS:
        result = subprocess.run(
            _docker_command(cargo_command),
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=900,
        )
        if result.returncode != 0:
            return _fail(name, (result.stdout + result.stderr).strip())
        if name == "coverage" and not _has_total_branch_coverage(result.stdout + result.stderr):
            return _fail(
                name,
                "branch coverage is below 100%. The Rust gate requires 100% line coverage and 100% branch coverage.",
            )
        passed.append(name)
    print(
        "[RUST GATE: "
        f"fmt={'pass' if 'fmt' in passed else 'fail'} "
        f"clippy={'pass' if 'clippy' in passed else 'fail'} "
        f"tests={'pass' if 'tests' in passed else 'fail'} "
        f"doc_tests={'pass' if 'doc_tests' in passed else 'fail'} "
        f"coverage={'100/100' if 'coverage' in passed else 'fail'} "
        f"mutants={'>=90' if 'mutants' in passed else 'fail'} "
        f"audit={'pass' if 'audit' in passed else 'fail'} "
        f"deny={'pass' if 'deny' in passed else 'fail'}]"
    )
    return 0


def _docker_command(cargo_command: str) -> list[str]:
    return [
        "docker",
        "compose",
        "exec",
        "-T",
        "compiled-tools",
        "bash",
        "-lc",
        f"cd {CONTAINER_WORKSPACE} && {cargo_command}",
    ]


def _has_total_branch_coverage(output: str) -> bool:
    for line in output.splitlines():
        fields = line.split()
        if fields and fields[0] == "TOTAL":
            return fields[-1] == "100.00%"
    return False


def _fail(step: str, detail: str) -> int:
    print(f"FAIL check-rust-mandate: {step}", file=sys.stderr)
    print(f"WHY: {detail or 'the Rust gate returned a non-zero result'}", file=sys.stderr)
    print("UNBLOCK: run the Docker-managed Rust gate and fix the named failure.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
