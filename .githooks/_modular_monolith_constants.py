"""Shared constants for modular-monolith and Go services-tier checks.

Promoted from inline constants in test_check_modular_monolith_docs.py during
slice 1.5 so the slice-1.5 hooks and tests can reuse them. Module name is
underscore-prefixed so it is treated as private by the rest of the
.githooks tree.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- Slice 1 (modular-monolith foundation) ---------------------------------

MODULAR_MONOLITH_DOC = REPO_ROOT / "docs" / "MODULAR-MONOLITH.md"
MODULE_DIR = REPO_ROOT / "docs" / "modules"
ADR_DIR = REPO_ROOT / "docs" / "adr"
SPEC_FILE = REPO_ROOT / "docs" / "specs" / "fr-modular-monolith.md"
PLAIN_ENGLISH_FILE = REPO_ROOT / "PLAIN-ENGLISH-RULE.md"
AGENTS_FILE = REPO_ROOT / "AGENTS.md"
CLAUDE_FILE = REPO_ROOT / "CLAUDE.md"
CODEX_FILE = REPO_ROOT / "CODEX.md"
GEMINI_FILE = REPO_ROOT / "GEMINI.md"
AI_CONTEXT_FILE = REPO_ROOT / "AI-CONTEXT.md"

RULE_FILES = (AGENTS_FILE, CLAUDE_FILE, CODEX_FILE, GEMINI_FILE)

# The 9 Django modules plus the services-tier name. Order matters for the
# docs/modules/ stub check.
MODULE_NAMES: tuple[str, ...] = (
    "platform",
    "content",
    "sources",
    "pipeline",
    "suggestions",
    "analytics",
    "graph",
    "operations",
    "governance",
    "services",
)

DJANGO_MODULE_NAMES: tuple[str, ...] = MODULE_NAMES[:-1]

ADR_NUMBERS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)

REQUIRED_DOC_PHRASES: tuple[str, ...] = (
    "module map",
    "public interface",
    "boundary rule",
    "dependency direction",
    "test plan",
    "stop condition",
)

REQUIRED_ADR_HEADINGS: tuple[str, ...] = ("Context", "Decision", "Consequences")

NEW_GLOSSARY_TERMS: tuple[str, ...] = (
    "modular monolith",
    "public interface",
    "boundary rule",
    "dependency direction",
    "ADR",
    "citation",
    "manifest",
    "shim",
    "deprecation",
    "golden test",
    "fitness function",
    "anti-corruption layer",
)

GLOSSARY_TERMS_REQUIRING_WORD_BOUNDARY: tuple[str, ...] = ("module",)

RULE_HEADER_RE = re.compile(
    r"^\*\*ABSOLUTE\s+[—-]\s+Modular Monolith", re.MULTILINE
)
SPEC_FRESHNESS_RE = re.compile(
    r"\[SPEC FRESHNESS:\s*reviewed_at=(\d{4}-\d{2}-\d{2})\s+"
    r"next_review=(\d{4}-\d{2}-\d{2})\]"
)
SPEC_CITED_RE = re.compile(
    r"\[SPEC CITED:\s*feature=([^\s]+)\s+kind=(\w+)\s+id=(\S+)\s+verified_at=([^\]]+)\]"
)

# --- Slice 1.5 (Go services tier) ------------------------------------------

SERVICES_DIR = REPO_ROOT / "services"

# A services-tier folder must publish ONE of these contract file names.
GO_CONTRACT_FILES: tuple[str, ...] = ("api.proto", "api.http.md")

# A services-tier folder must publish a binary entry point at this path,
# with {name} substituted for the service folder name.
GO_BINARY_ENTRY_TEMPLATE: str = "cmd/{name}/main.go"


def go_service_folders() -> list[Path]:
    """List every services/<name>/ folder that contains go.mod.

    Used by the contract-presence hook and the layer-fence test.
    """
    if not SERVICES_DIR.is_dir():
        return []
    folders: list[Path] = []
    for child in sorted(SERVICES_DIR.iterdir()):
        if not child.is_dir():
            continue
        if (child / "go.mod").is_file():
            folders.append(child)
    return folders


def go_service_binary_path(service_folder: Path) -> Path:
    """Return the required cmd/<name>/main.go path for a services tier folder."""
    return service_folder / GO_BINARY_ENTRY_TEMPLATE.format(name=service_folder.name)


def go_service_contract_paths(service_folder: Path) -> list[Path]:
    """Return every legal contract file path for a services tier folder."""
    return [service_folder / name for name in GO_CONTRACT_FILES]
