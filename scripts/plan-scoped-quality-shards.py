#!/usr/bin/env python3
"""Scoped MegaLinter file-level shard planner.

Assigns changed + affected files to Mint for MegaLinter, then emits a
JSON manifest for the orchestrator. Language-specific jobs still use the
turbo orchestrator's Windows/Mint split.

Reuses: commit_scope, quality_cores.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import commit_scope  # noqa: E402

# Cost by file extension (higher = more expensive to lint).
COST_BY_EXT: dict[str, int] = {
    ".md": 1, ".rst": 1, ".yml": 1, ".yaml": 1, ".json": 1, ".toml": 1,
    ".sh": 2, ".ps1": 2, ".py": 2, ".ts": 2, ".tsx": 2,
    ".go": 5, ".rs": 5, ".hs": 5,
    ".cpp": 6, ".cc": 6, ".cxx": 6, ".c": 6, ".h": 6, ".hpp": 6,
}
DEFAULT_COST = 2
DISPOSABLE_PATH_PREFIXES: tuple[str, ...] = (
    ".antigravitycli/",
    ".tmp/",
    "audit/",
    "backend/.mutmut-cache/",
    "backend/tmp/",
    "frontend/.stryker-tmp/",
    "reports/",
    "tmp/",
)
DISPOSABLE_PATH_NAMES: frozenset[str] = frozenset(
    {
        "luacov.stats.out",
    }
)
DISPOSABLE_ROOT_GLOBS: tuple[str, ...] = (
    "findbugs-",
)
DISPOSABLE_PATH_PARTS: frozenset[str] = frozenset(
    {
        ".pytest_cache",
        ".ruff_cache",
        ".stryker-tmp",
        "__pycache__",
        "htmlcov",
    }
)


def _normalized_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized


def is_disposable_artifact(path: str) -> bool:
    """Return true for generated quality output that should not drive sharding."""
    normalized = _normalized_path(path)
    if normalized.startswith(DISPOSABLE_PATH_PREFIXES):
        return True
    name = Path(normalized).name
    if name in DISPOSABLE_PATH_NAMES:
        return True
    if "/" not in normalized and normalized.endswith(".png"):
        return normalized.startswith(DISPOSABLE_ROOT_GLOBS)
    return any(part in DISPOSABLE_PATH_PARTS for part in normalized.split("/"))

def _cost(path: str) -> int:
    ext = Path(path).suffix.lower()
    return COST_BY_EXT.get(ext, DEFAULT_COST)


def build_manifest(
    changed_files: list[str],
    windows_cpus: int,
    mint_cpus: int,
) -> dict:
    """Assign files to Windows/Mint and return the JSON manifest dict."""
    if not changed_files:
        return {
            "changed_files": [],
            "affected_files": [],
            "windows_megalinter_paths": [],
            "mint_megalinter_paths": [],
            "windows_workers": windows_cpus,
            "mint_workers": mint_cpus,
            "blocking_scope": [],
            "weight_proof": {
                "total_cost": 0,
                "windows_cost": 0,
                "mint_cost": 0,
                "windows_pct": 0.0,
                "mint_pct": 0.0,
            },
        }

    changed_files = [path for path in changed_files if not is_disposable_artifact(path)]
    if not changed_files:
        return {
            "changed_files": [],
            "affected_files": [],
            "windows_megalinter_paths": [],
            "mint_megalinter_paths": [],
            "windows_workers": windows_cpus,
            "mint_workers": mint_cpus,
            "blocking_scope": [],
            "weight_proof": {
                "total_cost": 0,
                "windows_cost": 0,
                "mint_cost": 0,
                "windows_pct": 0.0,
                "mint_pct": 0.0,
            },
        }

    # Sort by cost desc then path asc for deterministic greedy assignment.
    sorted_files = sorted(changed_files, key=lambda p: (-_cost(p), p))
    total_cost = sum(_cost(p) for p in sorted_files)
    windows_files: list[str] = []
    mint_files: list[str] = sorted_files
    windows_cost = 0
    mint_cost = total_cost
    w_pct = 0.0
    m_pct = 100.0 if total_cost else 0.0

    return {
        "changed_files": changed_files,
        "affected_files": changed_files,
        "windows_megalinter_paths": windows_files,
        "mint_megalinter_paths": mint_files,
        "windows_workers": windows_cpus,
        "mint_workers": mint_cpus,
        "blocking_scope": changed_files,
        "weight_proof": {
            "total_cost": total_cost,
            "windows_cost": windows_cost,
            "mint_cost": mint_cost,
            "windows_pct": w_pct,
            "mint_pct": m_pct,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scoped MegaLinter shard planner")
    parser.add_argument(
        "--mode",
        default=os.environ.get("COMMIT_SCOPE_MODE", "staged"),
        choices=["staged", "push", "worktree"],
    )
    args = parser.parse_args()

    changed = commit_scope.paths_for_mode(REPO_ROOT, args.mode)
    win_cpus = 0
    mint_cpus = int(os.environ.get("MINT_WORKERS", "8"))

    manifest = build_manifest(changed, win_cpus, mint_cpus)
    manifest["scope_mode"] = args.mode
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
