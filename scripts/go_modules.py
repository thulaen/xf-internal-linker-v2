#!/usr/bin/env python3
"""Find Go modules touched by a set of paths.

Prints one absolute module path per line (paths are container-absolute, e.g.
`/repo/services/streamd`). Used by every `scripts/run-go-*.sh` sub-script so
the per-stage logic does not duplicate module discovery.

Usage inside the compiled-tools container:

    python /repo/scripts/go_modules.py --paths-env QUALITY_GO_PATHS
    python /repo/scripts/go_modules.py services/streamd/cmd/streamd/main.go
    python /repo/scripts/go_modules.py            # lists every go.mod in /repo

This file replaces the module-discovery half of the deleted
`scripts/check_go_tools.py`; the per-stage tool invocations (gofmt, vet,
staticcheck, etc.) live in the matching `scripts/run-go-<stage>.sh`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/repo"))
IGNORED_DIRS = {".git", "vendor", "node_modules", "build", "build_tests", "dist"}
GO_EXTENSIONS = (".go",)
GO_MOD_FILES = ("go.mod", "go.sum")
PROTO_EXTENSIONS = (".proto",)


def _module_for(path: Path) -> Path | None:
    """Walk up from `path` to find the nearest ancestor containing go.mod."""
    candidate = path
    if candidate.exists() and candidate.is_file():
        candidate = candidate.parent
    while candidate != REPO_ROOT.parent:
        if (candidate / "go.mod").is_file():
            return candidate
        if candidate == REPO_ROOT:
            return None
        candidate = candidate.parent
    return None


def _all_modules() -> list[Path]:
    """Walk the repo for every go.mod we own."""
    modules: list[Path] = []
    for current, dirs, filenames in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        if "go.mod" in filenames:
            modules.append(Path(current))
    return sorted(modules)


def _modules_for_paths(paths: list[str]) -> list[Path]:
    """Return the Go modules owning the given path strings, sorted unique."""
    seen: set[Path] = set()
    modules: list[Path] = []
    for raw in paths:
        if not raw.endswith((*GO_EXTENSIONS, *GO_MOD_FILES, *PROTO_EXTENSIONS)):
            continue
        full = (REPO_ROOT / raw).resolve()
        module = _module_for(full)
        if module is not None and module not in seen:
            seen.add(module)
            modules.append(module)
    return sorted(modules)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths-env",
        default=None,
        help="Read newline-separated paths from this env var.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Repo-relative file paths.",
    )
    args = parser.parse_args(argv)
    paths: list[str] = list(args.paths)
    if args.paths_env:
        env_value = os.environ.get(args.paths_env, "").strip()
        if env_value:
            paths.extend(
                line.strip() for line in env_value.splitlines() if line.strip()
            )
    if paths:
        modules = _modules_for_paths(paths)
    else:
        modules = _all_modules()
    for module in modules:
        print(module)
    return 0


if __name__ == "__main__":
    sys.exit(main())
