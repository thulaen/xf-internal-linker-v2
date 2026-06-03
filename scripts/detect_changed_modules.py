#!/usr/bin/env python3
"""Phase J: detect which per-language modules need mutation testing on CI.

Reads `git diff --name-only <base>...HEAD` and groups changed files by
language. The GitHub Actions workflow consumes this output to decide
which scoped mutation tools to run.

Usage:
    python scripts/detect_changed_modules.py --base origin/master --format json

Output (JSON):
    {
      "angular": [
        "frontend/src/app/error-log/error-log.component.ts",
        "frontend/src/app/error-log/sidecars-data.service.ts"
      ],
      "python": [
        "backend/apps/audit/services/audit_logger.py"
      ],
      "go": [
        "services/streamd/internal/publish.go"
      ],
      "cpp": [
        "backend/extensions/scoring.cpp"
      ],
      "any_mutation_targets": true
    }

The Angular bucket excludes *.spec.ts (test files); same for
.test.ts. The Python bucket excludes tests/*.py and test_*.py.
Go and C++ buckets follow the same convention.

Empty buckets are still present (as empty arrays) so the workflow
can use a single jq filter without branching.

Per the user policy: "GitHub PR CI must run scoped mutation only for
changed modules that require mutation". This script is the input.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COVERAGE_MODULES_YAML = REPO_ROOT / "coverage-modules.yaml"

_ANGULAR_INCLUDE = re.compile(r"^frontend/src/app/.*\.(component|service)\.ts$")
_ANGULAR_EXCLUDE = re.compile(r"\.(spec|test)\.ts$")

_PYTHON_INCLUDE = re.compile(r"^backend/apps/.*\.py$|^backend/config/.*\.py$")
_PYTHON_EXCLUDE = re.compile(
    r"(^|/)tests?/|(^|/)test_[^/]+\.py$|(^|/)tests_[^/]+\.py$|"
    r"(^|/)migrations/|(^|/)__init__\.py$"
)

_GO_INCLUDE = re.compile(r"^services/[^/]+/.*\.go$")
_GO_EXCLUDE = re.compile(r"_test\.go$|(^|/)api/gen/|(^|/)_sidecars_pb/")

_CPP_INCLUDE = re.compile(r"^backend/extensions/.*\.(cpp|h)$")
_CPP_EXCLUDE = re.compile(r"(^|/)tests?/|test_[^/]+\.cpp$|_test\.cpp$")


def _changed_files(base: str) -> list[str]:
    """Return staged + branch-against-base changed files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [
        line.strip().replace("\\", "/")
        for line in (result.stdout or "").splitlines()
        if line.strip()
    ]


def _classify(files: list[str]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {
        "angular": [],
        "python": [],
        "go": [],
        "cpp": [],
    }
    for path in files:
        if _ANGULAR_INCLUDE.match(path) and not _ANGULAR_EXCLUDE.search(path):
            buckets["angular"].append(path)
        elif _PYTHON_INCLUDE.match(path) and not _PYTHON_EXCLUDE.search(path):
            buckets["python"].append(path)
        elif _GO_INCLUDE.match(path) and not _GO_EXCLUDE.search(path):
            buckets["go"].append(path)
        elif _CPP_INCLUDE.match(path) and not _CPP_EXCLUDE.search(path):
            buckets["cpp"].append(path)
    # Sort for stable output.
    for key in buckets:
        buckets[key].sort()
    return buckets


# ---------------------------------------------------------------------------
# K2: modular-monolith module mapping. Reads coverage-modules.yaml and
# emits a {module: [files...]} dict. Strictest tier wins on overlap.
# ---------------------------------------------------------------------------

_TIER_RANK = {
    "tier1": 3,
    "tier2": 2,
    "tier3": 1,
    "cpp": 4,
    "go_streamd": 3,
    "go_sidecar": 3,
    "angular_component": 4,
    "angular_service": 4,
    "smoke": 0,
}


def _load_module_config() -> dict | None:
    """Return the parsed yaml or None if missing/unreadable."""
    if not COVERAGE_MODULES_YAML.is_file():
        return None
    try:
        import yaml  # PyYAML is in requirements.txt
    except ImportError:
        return None
    try:
        return yaml.safe_load(COVERAGE_MODULES_YAML.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def _match_glob(glob: str, path: str) -> bool:
    """fnmatch with `**` support (treat as `*`)."""
    if "**" in glob:
        # fnmatch's `**` is equivalent to `*` for our purposes — both
        # match any number of path segments. Simplify the glob.
        head, _, tail = glob.partition("**")
        head = head.rstrip("/")
        tail = tail.lstrip("/")
        if head and not (path.startswith(head + "/") or path == head):
            return False
        if tail and not fnmatch.fnmatch(path, "*" + tail):
            return False
        return True
    return fnmatch.fnmatch(path, glob)


def _classify_by_module(files: list[str]) -> dict[str, list[str]]:
    cfg = _load_module_config()
    if cfg is None:
        return {}
    modules_cfg = cfg.get("modules") or {}
    tiers_cfg = cfg.get("tiers") or {}
    # For each file, find the strictest matching module.
    file_module: dict[str, tuple[str, int]] = {}
    for path in files:
        for module_name, module_def in modules_cfg.items():
            tier_name = module_def.get("tier") or "tier3"
            rank = _TIER_RANK.get(tier_name, 0)
            globs = module_def.get("globs") or []
            excludes = module_def.get("exclude") or []
            if any(_match_glob(g, path) for g in globs) and not any(
                _match_glob(e, path) for e in excludes
            ):
                current = file_module.get(path)
                if current is None or rank > current[1]:
                    file_module[path] = (module_name, rank)
    # Invert: module -> [files]
    module_files: dict[str, list[str]] = {}
    for path, (module, _rank) in file_module.items():
        module_files.setdefault(module, []).append(path)
    for k in module_files:
        module_files[k].sort()
    return module_files


def tier_for_path(path: str) -> str | None:
    """Return the strictest matching tier name for one file.

    Falls back to ``default_tier`` when the file matches no module glob, and
    returns ``None`` only when the config itself is missing/unreadable. Shared
    by the per-file coverage gate and the scoped mutation gate so all three
    consumers (CI module detection, coverage, mutation) agree on tiers.
    """
    cfg = _load_module_config()
    if cfg is None:
        return None
    modules_cfg = cfg.get("modules") or {}
    best: tuple[str, int] | None = None
    for _name, mdef in modules_cfg.items():
        tier_name = mdef.get("tier") or cfg.get("default_tier", "tier3")
        rank = _TIER_RANK.get(tier_name, 0)
        globs = mdef.get("globs") or []
        excludes = mdef.get("exclude") or []
        if any(_match_glob(g, path) for g in globs) and not any(
            _match_glob(e, path) for e in excludes
        ):
            if best is None or rank > best[1]:
                best = (tier_name, rank)
    return best[0] if best else cfg.get("default_tier", "tier3")


def tier_thresholds(path: str) -> dict | None:
    """Return the ``{line, branch, mutation, ...}`` dict for a file's tier."""
    cfg = _load_module_config()
    if cfg is None:
        return None
    tier = tier_for_path(path)
    if tier is None:
        return None
    return (cfg.get("tiers") or {}).get(tier)


def tier_line_floor(path: str) -> int | None:
    """Return the minimum line-coverage percent for a file, or None."""
    spec = tier_thresholds(path)
    return None if spec is None else spec.get("line")


def tier_mutation_floor(path: str) -> int | None:
    """Return the minimum mutation-kill percent for a file, or None."""
    spec = tier_thresholds(path)
    return None if spec is None else spec.get("mutation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("XF_DIFF_BASE", "origin/master"),
                        help="Git ref to diff against. Default: origin/master.")
    parser.add_argument("--format", default="json", choices=("json", "shell"),
                        help="Output format. 'json' for jq pipelines; 'shell' for sourceable export lines.")
    opts = parser.parse_args()

    files = _changed_files(opts.base)
    buckets = _classify(files)
    modules = _classify_by_module(files)
    any_mutation_targets = any(len(v) > 0 for v in buckets.values())

    if opts.format == "json":
        payload = {
            **buckets,
            "modules": modules,
            "any_mutation_targets": any_mutation_targets,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    # shell format: export per-language space-separated lists.
    for lang, paths in buckets.items():
        joined = " ".join(paths)
        print(f"export XF_CHANGED_{lang.upper()}={joined!r}")
    print(f"export XF_ANY_MUTATION_TARGETS={'1' if any_mutation_targets else '0'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
