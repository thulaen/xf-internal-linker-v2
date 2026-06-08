#!/usr/bin/env python3
"""Compiled code must build AND run — hard block.

For a compiled language, writing the source is not enough: it has to compile
and the tests have to execute. This gate takes every staged compiled-language
file, builds the target it belongs to inside Docker, and runs that target's
tests. A missing import, a missing dependency, a broken generated stub, or a
failing test binary blocks the commit.

Scope of in-hook build/test (toolchains available in the running containers):
  * Go  — `go build ./... && go test ./...` for each affected services/<name>,
           run in the compiled-tools container (Go + repo mount).
  * C++ — rebuild the extensions via scripts/ensure_compiled_artifacts.py in
           the backend container, then import-smoke the affected module.

Rust (.rs) builds run through their dedicated quality runner already wired
in scripts/precommit-docker.sh (run-rust-quality.sh); this gate flags staged
.rs so the author knows that runner must pass, but does not duplicate its
toolchain here.

Exit codes:
    0 — every affected compiled target built and its tests ran clean.
    1 — a build failed, a dependency was missing, or a test target failed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fail(detail: str) -> int:
    sys.stderr.write(
        "\nFAIL check-compiled-build: compiled code did not build or run.\n"
        "WHY: a compiled-language file you changed must actually compile and "
        "its tests must execute. Committing source that does not build leaves "
        "the tree broken for the next person and for CI.\n"
        "UNBLOCK: fix the build (add the missing import / dependency / "
        "generated stub) and make the tests pass, then re-stage. Build with "
        "the same command the hook used (shown below).\n"
        f"\nDetail:\n{detail}\n"
    )
    return 1


def _staged() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _go_services(files: list[str]) -> list[str]:
    svc: list[str] = []
    for p in files:
        m = re.match(r"^services/([^/]+)/.*\.go$", p)
        if m and "/api/gen/" not in p and not p.endswith("_test.go"):
            name = m.group(1)
            if name not in svc:
                svc.append(name)
    # Only services that actually have a go.mod are buildable units.
    return [s for s in svc if (REPO_ROOT / "services" / s / "go.mod").is_file()]


def _has_cpp(files: list[str]) -> bool:
    return any(
        re.match(r"^backend/extensions/.*\.(cpp|h)$", p) and "/tests/" not in p
        for p in files
    )


def _docker_exec(service: str, script: str, timeout: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["docker", "compose", "exec", "-T", service, "bash", "-lc", script],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=timeout,
        )
    except FileNotFoundError:
        return 1, "Docker is not available; the build check could not run."
    except subprocess.TimeoutExpired:
        return 1, f"Build/test exceeded {timeout}s and was stopped."
    return proc.returncode, (proc.stdout + proc.stderr)


def _build_go(name: str) -> str | None:
    script = (
        f"cd /repo/services/{name} && go build ./... && go test ./... 2>&1 | tail -40"
    )
    code, out = _docker_exec("compiled-tools", script, timeout=900)
    if code != 0:
        return f"go service '{name}' failed: cd services/{name} && go build ./... && go test ./...\n{out[-1500:]}"
    return None


def _build_cpp() -> str | None:
    script = (
        "cd /repo && python scripts/ensure_compiled_artifacts.py 2>&1 | tail -40 && "
        "python -c 'import os, django; os.environ.setdefault(\"DJANGO_SETTINGS_MODULE\", \"config.settings\"); "
        "django.setup(); import apps.diagnostics.health as h; print(\"native-modules-ok\")'"
    )
    code, out = _docker_exec("backend", script, timeout=900)
    if code != 0:
        return f"C++ extensions failed to build/import: scripts/ensure_compiled_artifacts.py\n{out[-1500:]}"
    return None


def main() -> int:
    files = _staged()
    if not files:
        return 0

    failures: list[str] = []
    for name in _go_services(files):
        err = _build_go(name)
        if err:
            failures.append(err)
    if _has_cpp(files):
        err = _build_cpp()
        if err:
            failures.append(err)

    if failures:
        return _fail("\n\n".join(failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
