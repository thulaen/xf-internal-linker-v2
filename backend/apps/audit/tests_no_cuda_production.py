"""Guard that keeps GPU/CUDA code out of production paths.

Source-of-truth spec: docs/specs/fr-cpu-paid-embeddings-runtime.md.

This test deliberately ignores docs, tests, generated schemas, migrations,
vendored dependencies, caches, and build output. It exists to stop production
code from reintroducing the retired local GPU embedding/PageRank stack.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

from apps.audit.tests_glitchtip_compose_integrity import REPO_ROOT


PRODUCTION_ROOTS = (
    "backend/apps",
    "backend/config",
    "backend/requirements.txt",
    "config",
    "docker-compose.yml",
    "frontend/src/app",
    "scripts",
)

IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "migrations",
    "node_modules",
    "tmp",
}

IGNORED_NAME_PATTERNS = (
    re.compile(r"(^|[_-])test(s)?([_.-]|$)", re.IGNORECASE),
    re.compile(r"\.spec\.ts$", re.IGNORECASE),
    re.compile(r"schema\.d\.ts$", re.IGNORECASE),
)

FORBIDDEN_PATTERNS = (
    ("cuda", re.compile(r"cuda", re.IGNORECASE)),
    ("cupy", re.compile(r"cupy", re.IGNORECASE)),
    ("pynvml", re.compile(r"pynvml", re.IGNORECASE)),
    ("faiss-gpu", re.compile(r"faiss-gpu", re.IGNORECASE)),
    ("nvidia/cuda", re.compile(r"nvidia/cuda", re.IGNORECASE)),
    ("--gpus=all", re.compile(r"--gpus=all", re.IGNORECASE)),
)

TEXT_SUFFIXES = {
    ".html",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".scss",
    ".ts",
    ".txt",
    ".yml",
    ".yaml",
}


def _is_ignored(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    if any(part in IGNORED_PARTS for part in relative.parts):
        return True
    return any(pattern.search(path.name) for pattern in IGNORED_NAME_PATTERNS)


def _iter_production_files() -> list[Path]:
    files: list[Path] = []
    for root_name in PRODUCTION_ROOTS:
        root = REPO_ROOT / root_name
        if root.is_file():
            if root.suffix.lower() in TEXT_SUFFIXES and not _is_ignored(root):
                files.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                if not _is_ignored(path):
                    files.append(path)
    return sorted(files)


class NoCudaProductionTests(SimpleTestCase):
    def test_given_production_code_when_scanned_then_no_retired_gpu_terms_remain(self):
        offenders: list[str] = []
        for path in _iter_production_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, pattern in FORBIDDEN_PATTERNS:
                for match in pattern.finditer(text):
                    line_no = text.count("\n", 0, match.start()) + 1
                    rel_path = path.relative_to(REPO_ROOT).as_posix()
                    offenders.append(f"{rel_path}:{line_no} contains {label}")

        self.assertEqual(
            offenders,
            [],
            msg=(
                "Production code still contains retired GPU/CUDA references. "
                "Remove these entries or move historical text into ignored docs/tests: "
                + "; ".join(offenders[:50])
            ),
        )
