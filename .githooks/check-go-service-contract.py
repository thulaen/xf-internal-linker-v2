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

import re
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


def _rel(folder: Path, path: Path) -> Path:
    """Return path relative to REPO_ROOT when possible, else absolute."""
    if path.is_absolute():
        try:
            return path.relative_to(REPO_ROOT)
        except ValueError:
            return path
    return path


def _has_compose_entry(name: str) -> bool:
    """Return True if docker-compose.yml has a top-level service block for `name`."""
    compose = REPO_ROOT / "docker-compose.yml"
    if not compose.is_file():
        return False
    text = compose.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(rf"^\s{{2}}{re.escape(name)}:\s*$", re.MULTILINE)
    return bool(pattern.search(text))


def _has_generated_stubs(folder: Path) -> bool:
    """Return True if api/gen/*.pb.go exists for a service publishing api.proto.

    A service publishing api.http.md (HTTP+JSON) does not need generated
    Go stubs - that path is exempt from this check.
    """
    if not (folder / "api.proto").is_file():
        return True  # HTTP+JSON contract - no stubs to generate.
    gen_dir = folder / "api" / "gen"
    if not gen_dir.is_dir():
        return False
    return any(gen_dir.glob("*.pb.go"))


def scan_service_folder(folder: Path) -> list[Violation]:
    """Return all lifecycle violations for one service folder (Rule K).

    Checks the six lifecycle items together:
      1. go.mod (already required by _list_service_folders filter)
      2. api.proto OR api.http.md (the public RPC contract)
      3. cmd/<name>/main.go (the binary entry point)
      4. Dockerfile (multi-stage scratch build)
      5. Generated stubs in api/gen/ (only when api.proto exists)
      6. docker-compose.yml service block (so the sidecar actually runs)
    """
    violations: list[Violation] = []
    name = folder.name
    rel = _rel(folder, folder)
    # Item 1 - go.mod is the filter the caller already applied via
    # _list_service_folders. We still defensively re-check.
    if not (folder / "go.mod").is_file():
        violations.append(Violation(
            service=name, kind="go-mod",
            message=f"{rel}/go.mod is missing - every services/<name>/ folder needs a Go module.",
        ))
    # Item 2 - contract.
    contract_paths = [folder / cf for cf in _CONTRACT_FILES]
    if not any(p.is_file() for p in contract_paths):
        violations.append(Violation(
            service=name, kind="contract",
            message=(
                f"{rel}/ is missing both api.proto and api.http.md - every "
                f"Go service must publish ONE of api.proto (gRPC, preferred) "
                f"or api.http.md (HTTP+JSON) as its public RPC contract."
            ),
        ))
    # Item 3 - binary entry point.
    binary_path = folder / _BINARY_ENTRY_TEMPLATE.format(name=name)
    if not binary_path.is_file():
        violations.append(Violation(
            service=name, kind="binary",
            message=(
                f"{_rel(folder, binary_path)} is missing - library-only Go modules under "
                f"services/ are forbidden. Add a cmd/{name}/main.go binary "
                f"entry point so the service runs as a real sidecar, not "
                f"as a Python-loaded library."
            ),
        ))
    # Item 4 - Dockerfile.
    dockerfile = folder / "Dockerfile"
    if not dockerfile.is_file():
        violations.append(Violation(
            service=name, kind="dockerfile",
            message=(
                f"{_rel(folder, dockerfile)} is missing - every Go service ships a "
                f"multi-stage scratch Dockerfile so the sidecar deploys as a small "
                f"static binary. See services/streamd/Dockerfile for the template."
            ),
        ))
    # Item 5 - generated stubs (only when api.proto exists).
    if (folder / "api.proto").is_file() and not _has_generated_stubs(folder):
        violations.append(Violation(
            service=name, kind="stubs",
            message=(
                f"{rel}/api/gen/*.pb.go is missing - api.proto exists but no Go "
                f"stubs have been generated. Run `make -C {rel} proto` inside "
                f"the compiled-tools container and commit the generated stubs."
            ),
        ))
    # Item 6 - docker-compose service block.
    if not _has_compose_entry(name):
        violations.append(Violation(
            service=name, kind="compose",
            message=(
                f"docker-compose.yml has no `{name}:` service block - the sidecar "
                f"binary exists but nothing schedules it. Add a service entry that "
                f"builds {rel}/Dockerfile and mounts the {name}_sock named volume."
            ),
        ))
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
