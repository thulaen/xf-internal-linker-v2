#!/usr/bin/env python3
"""Select nearby pytest targets for changed backend Python files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _backend_relative(path: Path) -> Path:
    parts = path.as_posix().split("/")
    if parts and parts[0] == "backend":
        return Path(*parts[1:])
    return path


def _is_test_path(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("test_")
        or name.startswith("tests_")
        or name.endswith("_test.py")
        or "tests" in path.parts
    )


def _nearby_test_files(root: Path, directory: Path) -> list[Path]:
    host_dir = root / "backend" / directory
    if not host_dir.is_dir():
        return []
    return sorted(
        path.relative_to(root / "backend")
        for pattern in ("test*.py", "tests*.py")
        for path in host_dir.glob(pattern)
    )


def _has_tests(root: Path, directory: Path) -> bool:
    tests_dir = root / "backend" / directory / "tests"
    return bool(_nearby_test_files(root, directory) or tests_dir.exists())


def _app_root(path: Path) -> Path | None:
    parts = path.parts
    if len(parts) < 2 or parts[0] != "apps":
        return None
    return Path("apps") / parts[1]


def _existing_candidates(root: Path, backend_relative: Path) -> list[Path]:
    candidates: list[Path] = []
    parent = backend_relative.parent
    stem = backend_relative.stem
    candidates.extend(
        [
            parent / f"test_{stem}.py",
            parent / f"{stem}_test.py",
            parent / "tests.py",
        ]
    )
    app_root = _app_root(backend_relative)
    if app_root is not None:
        candidates.extend(
            [
                app_root / f"test_{stem}.py",
                app_root / "tests.py",
                app_root / "tests",
            ]
        )
        candidates.extend(_nearby_test_files(root, app_root))
    candidates.extend(_nearby_test_files(root, parent))
    return [path for path in candidates if (root / "backend" / path).exists()]


def select_targets(root: Path, changed_paths: list[str]) -> tuple[list[str], list[str]]:
    targets: list[str] = []
    missing: list[str] = []
    for item in changed_paths:
        backend_relative = _backend_relative(Path(item))
        if "migrations" in backend_relative.parts:
            continue
        elif backend_relative.parts and backend_relative.parts[0] == "config":
            candidates = [Path("config") / "tests.py", Path("config") / "tests"]
        elif app_root := _app_root(backend_relative):
            if _has_tests(root, app_root):
                targets.append(app_root.as_posix())
                continue
            candidates = [backend_relative] if _is_test_path(backend_relative) else []
        elif _is_test_path(backend_relative):
            candidates = [backend_relative]
        else:
            candidates = _existing_candidates(root, backend_relative)
        existing = [path for path in candidates if (root / "backend" / path).exists()]
        if existing:
            targets.extend(path.as_posix() for path in existing)
        elif not _is_test_path(backend_relative):
            missing.append(backend_relative.as_posix())
    return sorted(set(targets)), sorted(set(missing))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("changed_paths", nargs="+")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    targets, missing = select_targets(Path(args.repo_root).resolve(), args.changed_paths)
    if missing:
        print("Missing nearby pytest target for:", file=sys.stderr)
        for path in missing:
            print(path, file=sys.stderr)
        return 1
    for target in targets:
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
