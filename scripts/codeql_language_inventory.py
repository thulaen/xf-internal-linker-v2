"""Detect CodeQL-supported languages that are present in repository source."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath

SUPPORTED_ORDER = ["c-cpp", "go", "rust", "python", "javascript-typescript"]
UNSUPPORTED_REPORTED = {"haskell", "sql"}

EXTENSION_TO_LANGUAGE = {
    ".c": "c-cpp",
    ".cc": "c-cpp",
    ".cpp": "c-cpp",
    ".cxx": "c-cpp",
    ".h": "c-cpp",
    ".hh": "c-cpp",
    ".hpp": "c-cpp",
    ".hxx": "c-cpp",
    ".go": "go",
    ".rs": "rust",
    ".py": "python",
    ".js": "javascript-typescript",
    ".jsx": "javascript-typescript",
    ".ts": "javascript-typescript",
    ".tsx": "javascript-typescript",
    ".mjs": "javascript-typescript",
    ".cjs": "javascript-typescript",
    ".hs": "haskell",
    ".sql": "sql",
}

SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "coverage-html",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "dist-newstyle",
    "target",
    "tmp",
    "reports",
    "audit",
}

GENERATED_PREFIXES = (
    ("services", "sidecars", "api", "gen"),
    ("services", "streamd", "api", "gen"),
    ("backend", "apps", "realtime", "_streamd_pb2"),
)


@dataclass(frozen=True)
class LanguageInventory:
    """Detected CodeQL languages and unsupported language hints."""

    languages: list[str]
    unsupported_present: list[str]


def _git_files() -> list[str]:
    output = subprocess.check_output(["git", "ls-files"], text=True)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _normalise(path: str) -> PurePosixPath:
    return PurePosixPath(path.replace("\\", "/"))


def _is_generated(parts: tuple[str, ...], name: str) -> bool:
    if name.endswith(("_pb2.py", "_pb2_grpc.py", ".pb.go", "_grpc.pb.go")):
        return True
    return any(parts[: len(prefix)] == prefix for prefix in GENERATED_PREFIXES)


def should_scan_path(path: str) -> bool:
    """Return true when CodeQL should consider the path as handwritten source."""
    normalised = _normalise(path)
    parts = normalised.parts
    if any(part in SKIP_PARTS for part in parts):
        return False
    if "migrations" in parts and str(normalised).startswith("backend/apps/"):
        return False
    return not _is_generated(parts, normalised.name)


def detect_languages(paths: list[str] | None = None) -> LanguageInventory:
    """Detect supported CodeQL languages from tracked source files."""
    seen: set[str] = set()
    unsupported: set[str] = set()
    for path in paths if paths is not None else _git_files():
        if not should_scan_path(path):
            continue
        language = EXTENSION_TO_LANGUAGE.get(_normalise(path).suffix.lower())
        if language in SUPPORTED_ORDER:
            seen.add(language)
        elif language in UNSUPPORTED_REPORTED:
            unsupported.add(language)
    return LanguageInventory(
        languages=[language for language in SUPPORTED_ORDER if language in seen],
        unsupported_present=sorted(unsupported),
    )


def _github_matrix(inventory: LanguageInventory) -> dict:
    return {
        "include": [
            {
                "language": language,
                "build-mode": build_mode_for_language(language),
            }
            for language in inventory.languages
        ]
    }


def build_mode_for_language(language: str) -> str:
    """Return the CodeQL build mode used by this repository."""
    if language in {"c-cpp", "go"}:
        return "manual"
    return "none"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["plain", "json", "github-matrix"], default="plain")
    parser.add_argument("--from-list", nargs="*", default=None)
    args = parser.parse_args()
    inventory = detect_languages(args.from_list)
    if args.format == "github-matrix":
        print(json.dumps(_github_matrix(inventory), sort_keys=True))
    elif args.format == "json":
        print(json.dumps(inventory.__dict__, sort_keys=True))
    else:
        print(",".join(inventory.languages))
        if inventory.unsupported_present:
            print("unsupported-present=" + ",".join(inventory.unsupported_present))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
