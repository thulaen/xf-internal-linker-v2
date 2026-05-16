#!/usr/bin/env python3
"""Slice 1.5 — every services/<name>/ folder MUST publish a contract AND a binary.

Rule F-compliant (FAIL / WHY / UNBLOCK). Hard-block at commit.

What this hook enforces (per ADR 0006 § Decision points 1 and 6 and
docs/MODULAR-MONOLITH.md § Services tier rules 1 and 4):

  1. A services/<name>/ folder publishes its public RPC surface in one of
     services/<name>/api.proto (gRPC, preferred) or services/<name>/api.http.md
     (HTTP+JSON, fallback).

  2. A services/<name>/ folder publishes a binary entry point at
     services/<name>/cmd/<name>/main.go. Library-only Go modules under
     services/ are FORBIDDEN: the speed reason Go was chosen is the binary
     sidecar shape, not a library that Python loads.

The hook scans the on-disk services/ tree on every commit (cheap — there are
only a handful of services). It does not parse staged paths; the check is
service-folder-shaped, not file-shaped, so a partial commit cannot bypass it.

The helpers `scan_service_folder(folder)` and `scan_base_dir(base)` are exposed
for unit tests so the test suite never needs the real services/ tree.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Mutable module-level so tests can repoint without monkeypatching constants.
SERVICES_DIR: Path = REPO_ROOT / "services"

# Per the constants module (kept in sync intentionally so the hook stays
# self-contained even if _modular_monolith_constants moves).
_CONTRACT_FILES = ("api.proto", "api.http.md")
_BINARY_ENTRY_TEMPLATE = "cmd/{name}/main.go"


@dataclass(frozen=True)
class Violation:
    service: str
    kind: str  # "contract" or "binary"
    message: str


def _list_service_folders(base: Path) -> list[Path]:
    """Return the immediate child folders of `base` that contain a go.mod."""
    if not base.is_dir():
        return []
    folders: list[Path] = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "go.mod").is_file():
            folders.append(child)
    return folders


def scan_service_folder(folder: Path) -> list[Violation]:
    """Return all contract / binary violations for one service folder."""
    violations: list[Violation] = []
    name = folder.name
    rel = folder
    if folder.is_absolute():
        try:
            rel = folder.relative_to(REPO_ROOT)
        except ValueError:
            # Test fixtures live outside REPO_ROOT — keep the absolute display.
            rel = folder
    contract_paths = [folder / cf for cf in _CONTRACT_FILES]
    if not any(p.is_file() for p in contract_paths):
        violations.append(
            Violation(
                service=name,
                kind="contract",
                message=(
                    f"{rel}/ is missing both api.proto and api.http.md — every "
                    f"Go service must publish ONE of api.proto (gRPC, preferred) "
                    f"or api.http.md (HTTP+JSON) as its public RPC contract."
                ),
            )
        )
    binary_path = folder / _BINARY_ENTRY_TEMPLATE.format(name=name)
    if not binary_path.is_file():
        rel_binary = binary_path
        if binary_path.is_absolute():
            try:
                rel_binary = binary_path.relative_to(REPO_ROOT)
            except ValueError:
                rel_binary = binary_path
        violations.append(
            Violation(
                service=name,
                kind="binary",
                message=(
                    f"{rel_binary} is missing — library-only Go modules under "
                    f"services/ are forbidden. Add a cmd/{name}/main.go binary "
                    f"entry point so the service runs as a real sidecar, not "
                    f"as a Python-loaded library."
                ),
            )
        )
    return violations


def scan_base_dir(base: Path) -> list[Violation]:
    """Walk `base/services/` (or `base` directly if it ends in /services) and
    aggregate violations for every service folder."""
    services_root = base / "services" if base.name != "services" else base
    violations: list[Violation] = []
    for folder in _list_service_folders(services_root):
        violations.extend(scan_service_folder(folder))
    return violations


def _format_failure(violations: Iterable[Violation]) -> str:
    body = [
        "FAIL check-go-service-contract: at least one services/<name>/ folder "
        "is missing its required artefacts.",
        "WHY: ADR 0006 § Decision (points 1 and 6) and docs/MODULAR-MONOLITH.md "
        "§ Services tier (rules 1 and 4) require every Go service to publish: "
        "(a) ONE of api.proto / api.http.md as its public RPC contract, AND "
        "(b) cmd/<name>/main.go as its binary entry point. Library-only Go "
        "modules under services/ defeat the speed reason Go was chosen — they "
        "re-couple the build, encourage cross-language imports, and lose the "
        "sidecar deployment shape.",
        "UNBLOCK: For each violation below, add the missing artefact. For a "
        "contract, write services/<name>/api.proto using the gRPC pattern from "
        "services/streamd/api.proto (preferred) or services/<name>/api.http.md "
        "with a documented HTTP+JSON contract. For a binary, write "
        "services/<name>/cmd/<name>/main.go that exposes the contract over a "
        "Unix socket and exits cleanly on SIGTERM.",
    ]
    text = "\n".join(body) + "\n"
    for v in violations:
        text += f"  [{v.kind}] {v.service}: {v.message}\n"
    text += (
        "\nIf you believe this is a false positive, file the report first with:\n"
        "  docker compose exec -T backend python manage.py "
        "report_hook_false_positive --hook check-go-service-contract "
        "--context \"<plain-English explanation>\"\n"
    )
    return text


def main() -> int:
    if not SERVICES_DIR.is_dir():
        return 0
    folders = _list_service_folders(SERVICES_DIR)
    violations: list[Violation] = []
    for folder in folders:
        violations.extend(scan_service_folder(folder))
    if not violations:
        return 0
    sys.stderr.write(_format_failure(violations))
    return 2


if __name__ == "__main__":
    sys.exit(main())
