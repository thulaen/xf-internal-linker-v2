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


def _compose_mounts_socket(name: str) -> bool:
    """Return True if docker-compose.yml declares a named volume `<name>_sock`
    (the Unix-domain socket convention from ADR 0006 / docs/MODULAR-MONOLITH.md).

    A service publishing api.http.md instead of api.proto is exempt because
    HTTP+JSON typically uses TCP, not a Unix socket. The caller passes
    `is_grpc=True` only when api.proto is present.
    """
    compose = REPO_ROOT / "docker-compose.yml"
    if not compose.is_file():
        return False
    text = compose.read_text(encoding="utf-8", errors="replace")
    # Named-volume declaration under top-level `volumes:` block.
    volume_pattern = re.compile(rf"^\s{{2}}{re.escape(name)}_sock\s*:", re.MULTILINE)
    return bool(volume_pattern.search(text))


def _dockerfile_is_multi_stage(dockerfile: Path) -> bool:
    """Return True if the Dockerfile is multi-stage (>=2 FROM directives).

    Multi-stage builds keep the runtime image small (typically scratch + a
    single static binary). A single-stage build pulls a full toolchain image
    into production, which contradicts the speed/size argument for Go services.
    """
    if not dockerfile.is_file():
        return False
    text = dockerfile.read_text(encoding="utf-8", errors="replace")
    from_lines = re.findall(r"^\s*FROM\s+\S+", text, flags=re.MULTILINE)
    return len(from_lines) >= 2


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


def _go_sum_is_populated(folder: Path) -> bool:
    """Return True if go.sum exists and is non-empty.

    An empty go.sum means `go mod tidy` was never run after dependencies
    were declared in go.mod, which makes a reproducible build impossible.
    A service with zero declared dependencies (an empty go.mod `require ()`
    block) is exempt — return True so we do not block clean greenfield
    scaffolds.
    """
    gomod = folder / "go.mod"
    gosum = folder / "go.sum"
    if not gomod.is_file():
        return False
    gomod_text = gomod.read_text(encoding="utf-8", errors="replace")
    # A go.mod with no `require` directives or only an empty `require ()` is
    # legitimately depless and does not need a go.sum.
    has_requires = bool(re.search(r"^\s*require\s*\(", gomod_text, re.MULTILINE)) or bool(
        re.search(r"^\s*require\s+\S+\s+v\S+", gomod_text, re.MULTILINE)
    )
    if not has_requires:
        return True
    return gosum.is_file() and gosum.stat().st_size > 0


# quality-debt-ignore: reason: scan_service_folder checks 9 lifecycle items in sequence, each producing a different Violation kind with its own plain-English message; the function is long by design because every kind needs its own dedicated message that an operator can act on
def scan_service_folder(folder: Path) -> list[Violation]:
    """Return all lifecycle violations for one service folder (Rule K).

    Checks the nine lifecycle items together:
      1. go.mod (already required by _list_service_folders filter)
      2. api.proto OR api.http.md (the public RPC contract)
      3. cmd/<name>/main.go (the binary entry point)
      4. Dockerfile (multi-stage scratch build)
      5. Generated stubs in api/gen/ (only when api.proto exists)
      6. docker-compose.yml service block (so the sidecar actually runs)
      7. go.sum populated (reproducible builds; exempt when go.mod has no
         require directives)
      8. Dockerfile is multi-stage (>=2 FROM directives; keeps prod image small)
      9. docker-compose.yml declares `<name>_sock` named volume (gRPC services
         only; HTTP+JSON contract services are exempt)
    """
    violations: list[Violation] = []
    name = folder.name
    rel = _rel(folder, folder)
    # Item 1 - go.mod is the filter the caller already applied via
    # _list_service_folders. We still defensively re-check.
    if not (folder / "go.mod").is_file():
        # quality-debt-ignore: reason: each Rule K item appends its own Violation with its own kind name and message; the repeated violations.append(Violation(...)) shape is intrinsic per item
        violations.append(Violation(
            service=name, kind="go-mod",
            message=f"{rel}/go.mod is missing - every services/<name>/ folder needs a Go module.",
        ))
    # Item 2 - contract.
    contract_paths = [folder / cf for cf in _CONTRACT_FILES]
    has_proto = (folder / "api.proto").is_file()
    if not any(p.is_file() for p in contract_paths):
        # quality-debt-ignore: reason: each Rule K item appends its own Violation with its own kind name and message; the repeated violations.append(Violation(...)) shape is intrinsic per item
        violations.append(Violation(
            service=name, kind="contract",
            # quality-debt-ignore: reason: each kind's message is a distinct user-facing string with its own technical content; the repeated message= parameter shape is intentional
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
    if has_proto and not _has_generated_stubs(folder):
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
    # Item 7 - go.sum populated when go.mod has require directives.
    if (folder / "go.mod").is_file() and not _go_sum_is_populated(folder):
        violations.append(Violation(
            service=name, kind="go-sum",
            message=(
                f"{rel}/go.sum is missing or empty even though go.mod declares "
                f"dependencies. Run `go mod tidy` (inside the compiled-tools "
                f"container) and commit the resulting go.sum so the build is "
                f"reproducible."
            ),
        ))
    # Item 8 - multi-stage Dockerfile.
    if dockerfile.is_file() and not _dockerfile_is_multi_stage(dockerfile):
        violations.append(Violation(
            service=name, kind="dockerfile-shape",
            message=(
                f"{_rel(folder, dockerfile)} is single-stage. Every Go service must "
                f"use a multi-stage Dockerfile (>=2 FROM directives) so the runtime "
                f"image is small (scratch + static binary). A single-stage build "
                f"ships the full toolchain to production and defeats the speed "
                f"argument for Go services. See services/streamd/Dockerfile."
            ),
        ))
    # Item 9 - named-volume mount (gRPC services only).
    if has_proto and not _compose_mounts_socket(name):
        violations.append(Violation(
            service=name, kind="compose-volume",
            message=(
                f"docker-compose.yml has no `{name}_sock:` named volume. Every "
                f"gRPC Go service is expected to expose its server over a "
                f"Unix-domain socket carried by a `{name}_sock` named volume "
                f"that both the service and its Python client mount. See the "
                f"`streamd_sock` block in docker-compose.yml for the template. "
                f"Services that publish api.http.md (HTTP+JSON) instead of "
                f"api.proto are exempt."
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
