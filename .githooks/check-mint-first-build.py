#!/usr/bin/env python3
"""Pre-commit guard: builds must be mint-first (route through the build router).

config/docker-build-routing.json sets compilation to mint 65 / windows 35
(mint-first). A raw image-build invocation (the ``build`` subcommand of
``docker``, of ``docker compose``, or of ``docker buildx``) in a committed
script bypasses that router and always builds locally on Windows. This guard
blocks such raw build invocations in staged scripts and requires routing
through the smart build helper (``scripts/build-smart.ps1`` or
``scripts/smart_build.py``).

`docker compose run` / `up` are NOT builds and are not flagged. The router
scripts themselves are exempt because they must call the real image-build
subcommand directly.

Run manually:
    python .githooks/check-mint-first-build.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Matches: `docker build`, `docker compose build`, `docker-compose build`,
# `docker buildx build`. Does NOT match `docker compose run`/`up` (the token
# after the compose/buildx prefix would be `run`/`up`, not `build`).
_BUILD_RE = re.compile(r"\bdocker(?:-compose)?\s+(?:compose\s+|buildx\s+)?build\b")

# The router scripts MUST invoke the real docker build — exempt them.
_ROUTER_BASENAMES = frozenset({"smart_build.py", "build-smart.ps1"})
_PATH_ALLOWLIST = frozenset({".githooks/check-bazel-public-entrypoints.py"})

_SCANNED_EXTS = frozenset({".sh", ".ps1", ".py"})


def is_scanned_path(path: str) -> bool:
    """Return True if *path* is a script we should scan for raw builds."""
    p = path.replace("\\", "/")
    suffix = Path(p).suffix.lower()
    if suffix not in _SCANNED_EXTS:
        return False
    name = Path(p).name
    # Test files are not build-invocation scripts.
    if name.startswith("test_") or name.endswith("_test.py") or "/tests/" in p:
        return False
    return True


def scan_text(path: str, text: str) -> list[str]:
    """Return a list of violation messages for raw build commands in *text*."""
    normalised_path = path.replace("\\", "/")
    if normalised_path in _PATH_ALLOWLIST:
        return []
    name = Path(normalised_path).name
    if name in _ROUTER_BASENAMES:
        return []
    violations: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        if _BUILD_RE.search(raw):
            violations.append(
                f"  {path}:{lineno}: raw build command — route through "
                f"build-smart/smart_build instead: {stripped[:100]}"
            )
    return violations


def _staged_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
    except (FileNotFoundError, OSError):
        return []
    return [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]


def _staged_content(path: str) -> str:
    try:
        out = subprocess.run(
            ["git", "show", f":{path}"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
    except (FileNotFoundError, OSError):
        return ""
    return out.stdout or ""


def main() -> int:
    violations: list[str] = []
    for path in _staged_files():
        if not is_scanned_path(path):
            continue
        violations.extend(scan_text(path, _staged_content(path)))
    if not violations:
        return 0
    sys.stderr.write(
        "FAIL check-mint-first-build: a staged script invokes a raw docker "
        "build.\n"
        "WHY: config/docker-build-routing.json routes compilation mint-first "
        "(mint 65 / windows 35). A raw `docker " + "build`/`docker compose " +
        "build` "
        "bypasses the router and always builds locally on Windows.\n"
        "RAW BUILDS:\n" + "\n".join(violations) + "\n"
        "UNBLOCK: route the build through `scripts/build-smart.ps1 --target "
        "<svc>` (PowerShell) or `python scripts/smart_build.py --target <svc>` "
        "so it honours the 65/35 mint-first split.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
