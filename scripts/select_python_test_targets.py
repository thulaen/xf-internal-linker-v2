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


def _backend_root(root: Path) -> Path:
    return root / "backend"


def _is_test_path(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("test_")
        or name.startswith("tests_")
        or name.endswith("_test.py")
        or "tests" in path.parts
    )


def _nearby_test_files(root: Path, directory: Path) -> list[Path]:
    host_dir = _backend_root(root) / directory
    if not host_dir.is_dir():
        return []
    return sorted(
        path.relative_to(_backend_root(root))
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
            parent / f"tests_{stem}.py",
            parent / f"{stem}_test.py",
            parent / "tests.py",
        ]
    )
    app_root = _app_root(backend_relative)
    if app_root is not None:
        candidates.extend(
            [
                app_root / f"test_{stem}.py",
                app_root / f"tests_{stem}.py",
                app_root / "tests" / f"test_{stem}.py",
                app_root / "tests" / f"tests_{stem}.py",
                app_root / "tests" / f"{stem}_test.py",
                app_root / "tests.py",
            ]
        )
    candidates.extend(_nearby_test_files(root, parent))
    candidates.extend(_import_based_test_files(root, backend_relative))
    candidates.extend(_management_command_test_files(root, backend_relative))
    candidates.extend(_same_app_named_test_files(root, backend_relative))
    return [path for path in candidates if (root / "backend" / path).exists()]


def _same_app_test_files(root: Path, backend_relative: Path) -> list[Path]:
    search_root = _same_app_search_root(root, backend_relative)
    if search_root is None:
        return []
    return sorted(
        path.relative_to(_backend_root(root))
        for path in search_root.rglob("*.py")
        if _is_test_path(path.relative_to(_backend_root(root)))
    )


def _same_app_search_root(root: Path, backend_relative: Path) -> Path | None:
    app_root = _app_root(backend_relative)
    if app_root is None:
        return None
    search_root = _backend_root(root) / app_root
    if not search_root.is_dir():
        return None
    return search_root


def _module_needles(backend_relative: Path) -> set[str]:
    module = ".".join(backend_relative.with_suffix("").parts)
    needles = {module, f"apps.{module.removeprefix('apps.')}"}
    if "services" in backend_relative.parts:
        needles.add(backend_relative.stem)
    return needles


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def _import_based_test_files(root: Path, backend_relative: Path) -> list[Path]:
    if backend_relative.suffix != ".py" or _is_test_path(backend_relative):
        return []
    needles = _module_needles(backend_relative)
    search_root = _same_app_search_root(root, backend_relative)
    if search_root is None:
        return []
    matches: list[Path] = []
    for test_path in search_root.rglob("*.py"):
        rel = test_path.relative_to(_backend_root(root))
        if not _is_test_path(rel):
            continue
        text = _read_text(test_path)
        if any(needle in text for needle in needles):
            matches.append(rel)
    return sorted(matches)


def _management_command_name(path: Path) -> str | None:
    parts = path.parts
    if len(parts) < 4:
        return None
    if parts[-3:-1] != ("management", "commands"):
        return None
    return path.stem


def _management_command_test_files(root: Path, backend_relative: Path) -> list[Path]:
    command_name = _management_command_name(backend_relative)
    if command_name is None:
        return []
    quoted_names = {
        f"call_command('{command_name}'",
        f'call_command("{command_name}"',
        f"call_command(\n            '{command_name}'",
        f'call_command(\n            "{command_name}"',
    }
    matches: list[Path] = []
    for rel in _same_app_test_files(root, backend_relative):
        text = _read_text(_backend_root(root) / rel)
        quoted_command = f"'{command_name}'" in text or f'"{command_name}"' in text
        if any(name in text for name in quoted_names) or (
            "call_command" in text and quoted_command
        ):
            matches.append(rel)
    return sorted(matches)


def _same_app_named_test_files(root: Path, backend_relative: Path) -> list[Path]:
    if backend_relative.suffix != ".py" or _is_test_path(backend_relative):
        return []
    stem = backend_relative.stem
    return [
        rel
        for rel in _same_app_test_files(root, backend_relative)
        if stem in rel.stem
    ]


def _generated_sidecar_contract_tests(root: Path, backend_relative: Path) -> list[Path]:
    if backend_relative.suffix != ".py":
        return []
    if len(backend_relative.parts) < 3:
        return []
    if backend_relative.parts[:2] != ("apps", "_sidecars_pb"):
        return []
    contract = Path("apps") / "_sidecars_shared" / "tests_sidecar_contract.py"
    if (root / "backend" / contract).exists():
        return [contract]
    return []


def _candidate_tests_for_path(root: Path, backend_relative: Path) -> list[Path]:
    if backend_relative.parts and backend_relative.parts[0] == "config":
        return [Path("config") / "tests.py", Path("config") / "tests"]
    if _is_test_path(backend_relative):
        return [backend_relative]
    generated_sidecar_tests = _generated_sidecar_contract_tests(root, backend_relative)
    if generated_sidecar_tests:
        return generated_sidecar_tests
    return _existing_candidates(root, backend_relative)


def select_targets(root: Path, changed_paths: list[str]) -> tuple[list[str], list[str]]:
    targets: list[str] = []
    missing: list[str] = []
    for item in changed_paths:
        backend_relative = _backend_relative(Path(item))
        if backend_relative.name == "__init__.py":
            continue
        if "migrations" in backend_relative.parts:
            continue
        candidates = _candidate_tests_for_path(root, backend_relative)
        existing = [path for path in candidates if (_backend_root(root) / path).exists()]
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
