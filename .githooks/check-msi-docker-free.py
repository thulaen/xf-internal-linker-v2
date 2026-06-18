#!/usr/bin/env python3
"""Block normal repo paths from requiring MSI Docker."""

from __future__ import annotations

import re
import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXECUTABLE_SUFFIXES = {".py", ".sh", ".ps1", ".psm1", ".cmd", ".bat"}
DOC_SUFFIXES = {".md", ".rst", ".txt"}

PATH_ALLOWLIST = {
    ".githooks/check-msi-docker-free.py",
    ".githooks/check-mint-first-build.py",
    ".githooks/check-no-parallel-quality.py",
    "scripts/banner_superseded_plans.py",
    "scripts/destructive_command_guard.py",
    "scripts/remote_docker.py",
    "scripts/dell_docker.py",
    "scripts/remove-msi-docker.ps1",
    "scripts/reclaim-docker-windows-space.ps1",
    "scripts/_quality_concurrency.sh",
    "scripts/run-python-quality.sh",
    "tools/quality/internal/run-python-quality.sh",
    "tools/quality/internal/run-angular-quality.sh",
    "tools/quality/internal/run-rust-quality.sh",
}

DIR_EXCLUDES = {
    ".git",
    ".claude",
    ".tmp",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    ".stryker-tmp",
    "dist",
    "build",
    "target",
    "tmp",
}

DOC_HISTORICAL_MARKERS = (
    "historical",
    "retired",
    "superseded",
    "legacy",
    "archive",
)

PATTERNS = (
    re.compile(r"\bdocker\s+compose\s+(exec|run|up|ps|build|down|rm)\b"),
    re.compile(r"\bdocker-compose\s+(exec|run|up|ps|build|down|rm)\b"),
    re.compile(r"\bdocker\s+--context\s+(default|desktop-linux|desktop-windows)\b"),
    re.compile(r"\bdocker\s+(ps|stats|volume\s+prune|system\s+prune)\b"),
    re.compile(r"Docker Desktop"),
)


def _normalise(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _is_remote_docker_line(line: str) -> bool:
    lowered = line.lower()
    return "ssh " in lowered and " docker " in lowered


def _is_retired_script(text: str) -> bool:
    head = "\n".join(text.splitlines()[:8]).lower()
    return "retired" in head


def _is_historical_doc(path: str, text: str) -> bool:
    lowered_path = path.lower()
    lowered_text = text[:8000].lower()
    return any(marker in lowered_path or marker in lowered_text for marker in DOC_HISTORICAL_MARKERS)


def scan_text(path: str, text: str) -> list[str]:
    """Return Docker-free guard violations for one file."""
    rel = _normalise(path)
    if rel in PATH_ALLOWLIST or _is_retired_script(text):
        return []
    if Path(rel).suffix.lower() in DOC_SUFFIXES and _is_historical_doc(rel, text):
        return []
    findings: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _should_skip_line(line):
            continue
        stripped = line.strip()
        if any(pattern.search(line) for pattern in PATTERNS):
            findings.append(f"{path}:{line_no}: {stripped[:160]}")
    return findings


def _should_skip_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#") and "Docker Desktop" not in stripped:
        return True
    return _is_remote_docker_line(line)


def _is_scan_candidate(path: Path) -> bool:
    excluded = (
        any(part in DIR_EXCLUDES for part in path.parts)
        or path.name.startswith(("test_", "tests_"))
        or path.name.endswith("_test.py")
        or any(part in {"tests", "reports", "specs", "migrations"} for part in path.parts)
    )
    if excluded:
        return False
    suffix = path.suffix.lower()
    is_doc = suffix in DOC_SUFFIXES and len(path.parts) >= 2 and path.parts[0] == "docs"
    return suffix in EXECUTABLE_SUFFIXES or is_doc


def iter_checked_files() -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in DIR_EXCLUDES]
        root_path = Path(root)
        for name in names:
            path = root_path / name
            try:
                rel = path.relative_to(REPO_ROOT)
                if path.is_file() and _is_scan_candidate(rel):
                    files.append(path)
            except OSError:
                continue
    return files


def main() -> int:
    findings: list[str] = []
    for path in iter_checked_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(f"{rel}: could not read file: {exc}")
            continue
        findings.extend(scan_text(rel, text))
    if not findings:
        print("[MSI DOCKER-FREE: passed]")
        return 0
    print("FAIL check-msi-docker-free: normal repo workflow still requires MSI Docker.", file=sys.stderr)
    print("WHY: MSI should work without Docker Desktop, a local daemon, or the Docker CLI.", file=sys.stderr)
    print("UNBLOCK: use Kubernetes, scripts/backend_manage.py, or SSH-to-Dell helpers instead.", file=sys.stderr)
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
