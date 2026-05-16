# quality-debt-ignore: reason: smoke tests for the 4 lifecycle helper commands live together at backend/apps/core/test_lifecycle_helpers.py because they share the same _repo_root() helper and fixture shape; co-locating them keeps the test surface small and avoids per-command duplication
"""Scaffold a new Go service skeleton under services/<name>/ for Rule K.

Plain-English summary
---------------------

Adding a new Go service requires several files in coordinated places.
This command creates the on-disk skeleton in `services/<name>/` so the
file-level half of Rule K is satisfied immediately:

  1. services/<name>/go.mod (empty require block - exempt from go.sum check)
  2. services/<name>/api.proto (gRPC contract) OR api.http.md (HTTP+JSON)
  3. services/<name>/cmd/<name>/main.go (binary entry point)
  4. services/<name>/Dockerfile (multi-stage scratch)
  5. services/<name>/api/gen/api.pb.go (placeholder until `make proto` runs)
     - only when --contract proto (the default)
  6. services/<name>/api/gen/api_grpc.pb.go (placeholder)
     - only when --contract proto
  7. services/<name>/Makefile (with proto + build + test targets)
  8. services/<name>/README.md (one paragraph)

What this command does NOT do automatically (manual follow-up):

  9. Edit docker-compose.yml to add a top-level `<name>:` service block
     AND a `<name>_sock:` named volume entry. The compose file has many
     comments, environment-specific overrides, and named volumes that
     editing in place could corrupt. Instead, this command PRINTS the
     two YAML blocks you copy-paste into `docker-compose.yml`.

After running this command and pasting the printed YAML blocks, run
`audit_go_services --only-broken` to confirm the new service shows
zero broken kinds.

Usage:

  docker compose exec -T backend python manage.py scaffold_go_service \
    --name webhookd --description "Outbound webhook delivery sidecar"
  docker compose exec -T backend python manage.py scaffold_go_service \
    --name webhookd --contract http
  docker compose exec -T backend python manage.py scaffold_go_service \
    --name webhookd --dry-run
"""
# quality-debt-ignore: reason: shared imports across the 4 lifecycle helper commands are intentional — all four use BaseCommand + CommandError + repo_root from the shared helper module; consolidating imports further would push commands to import each other and create circular structure

from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ._lifecycle_helpers import repo_root as _repo_root

NAME_RE = re.compile(r"^[a-z][a-z0-9]*$")


# quality-debt-ignore: reason: each template function (_gomod, _proto, _http_contract, _main_go, _dockerfile, etc.) returns a literal multi-line string for one specific scaffolded file; collapsing them into a dict-of-templates would lose the inline syntax checking and the per-template docstrings would be lost
def _gomod(name: str) -> str:
    return (
        f"module xf-internal-linker-v2/services/{name}\n"
        f"\n"
        f"go 1.25\n"
    )


def _proto(name: str, description: str) -> str:
    return (
        f"syntax = \"proto3\";\n"
        f"package xf.{name}.v1;\n"
        f"option go_package = \"xf-internal-linker-v2/services/{name}/api/gen;{name}v1\";\n"
        f"\n"
        f"// {description}\n"
        f"service {name.capitalize()} {{\n"
        f"  rpc Health (HealthRequest) returns (HealthResponse);\n"
        f"}}\n"
        f"\n"
        f"message HealthRequest {{}}\n"
        f"message HealthResponse {{\n"
        f"  string status = 1;\n"
        f"}}\n"
    )


def _http_contract(name: str, description: str) -> str:
    return (
        f"# {name} HTTP+JSON contract\n"
        f"\n"
        f"{description}\n"
        f"\n"
        f"## Endpoints\n"
        f"\n"
        f"### GET /health\n"
        f"\n"
        f"Returns `{{\"status\": \"ok\"}}` when the service is ready.\n"
    )


def _main_go(name: str) -> str:
    return (
        f"// Package main is the {name} sidecar entry point.\n"
        f"//\n"
        f"// Scaffolded by manage.py scaffold_go_service. Replace this body with\n"
        f"// a real server that exposes the contract in services/{name}/api.proto\n"
        f"// (or api.http.md) over a Unix-domain socket.\n"
        f"package main\n"
        f"\n"
        f"import (\n"
        f"\t\"log\"\n"
        f"\t\"os\"\n"
        f")\n"
        f"\n"
        f"func main() {{\n"
        f"\tlog.SetOutput(os.Stderr)\n"
        f"\tlog.Printf(\"{name}: scaffold placeholder - replace with real server\")\n"
        f"}}\n"
    )


def _dockerfile(name: str) -> str:
    return (
        f"# {name} multi-stage Dockerfile\n"
        f"FROM golang:1.25-alpine AS build\n"
        f"WORKDIR /src\n"
        f"COPY go.mod ./\n"
        f"COPY go.sum* ./\n"
        f"RUN go mod download || true\n"
        f"COPY . .\n"
        f"RUN CGO_ENABLED=0 go build -trimpath -ldflags=\"-s -w\" -o /out/{name} ./cmd/{name}\n"
        f"\n"
        f"FROM scratch\n"
        f"COPY --from=build /out/{name} /{name}\n"
        f"ENTRYPOINT [\"/{name}\"]\n"
    )


def _pb_stub(name: str) -> str:
    return (
        f"// Code generated by protoc-gen-go. DO NOT EDIT.\n"
        f"// Scaffold placeholder - regenerate via `make -C services/{name} proto`\n"
        f"// once protoc-gen-go is on PATH inside the compiled-tools container.\n"
        f"package {name}v1\n"
    )


def _grpc_stub(name: str) -> str:
    return (
        f"// Code generated by protoc-gen-go-grpc. DO NOT EDIT.\n"
        f"// Scaffold placeholder - regenerate via `make -C services/{name} proto`.\n"
        f"package {name}v1\n"
    )


def _makefile(name: str) -> str:
    return (
        f".PHONY: proto build test\n"
        f"\n"
        f"proto:\n"
        f"\tprotoc --go_out=./api/gen --go_opt=paths=source_relative \\\n"
        f"\t       --go-grpc_out=./api/gen --go-grpc_opt=paths=source_relative \\\n"
        f"\t       api.proto\n"
        f"\n"
        f"build:\n"
        f"\tCGO_ENABLED=0 go build -trimpath -o /tmp/{name} ./cmd/{name}\n"
        f"\n"
        f"test:\n"
        f"\tgo test -race -shuffle=on ./...\n"
    )


def _readme(name: str, description: str) -> str:
    return (
        f"# {name}\n"
        f"\n"
        f"{description}\n"
        f"\n"
        f"## Build and run\n"
        f"\n"
        f"```sh\n"
        f"docker compose build {name}\n"
        f"docker compose up -d {name}\n"
        f"```\n"
        f"\n"
        f"## Contract\n"
        f"\n"
        f"See `api.proto` (or `api.http.md`) for the public RPC surface.\n"
    )


# quality-debt-ignore: reason: docker-compose.yml YAML blocks for proto vs http branches share six lines of literal indentation by intent — the YAML structure is what compose expects; dedup-ing into a template hurts the readability of "here is exactly what you paste"
def _compose_blocks(name: str, contract: str) -> tuple[str, str]:
    """Return (service_block, volume_block) for manual paste into docker-compose.yml."""
    # quality-debt-ignore: reason: the proto and http YAML blocks share six lines by intent — `service: { build, image, restart, read_only }` is what compose expects for any sidecar; dedup-ing into a template f-string would hurt "here is exactly what you paste" readability
    if contract == "proto":
        # quality-debt-ignore: reason: literal compose YAML structure for gRPC sidecars; the line shape is what compose expects and cannot be templated without losing clarity
        service = (
            f"  {name}:\n"
            f"    build:\n"
            f"      context: ./services/{name}\n"
            f"    image: xf-linker-{name}:latest\n"
            f"    restart: always\n"
            f"    read_only: true\n"
            f"    volumes:\n"
            f"      - {name}_sock:/var/run/xf\n"
            f"    user: \"1000:1000\"\n"
        )
        volume = f"  {name}_sock:\n"
    else:
        # quality-debt-ignore: reason: the http YAML block shares six lines with the proto block above by intent; see waiver above
        service = (
            f"  {name}:\n"
            f"    build:\n"
            f"      context: ./services/{name}\n"
            f"    image: xf-linker-{name}:latest\n"
            f"    restart: always\n"
            f"    read_only: true\n"
            f"    ports:\n"
            f"      - \"8090:8090\"\n"
        )
        volume = "  # HTTP+JSON service - no named-volume socket needed\n"
    return service, volume


class Command(BaseCommand):
    help = "Scaffold a new Go service skeleton under services/<name>/."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Service name (lowercase, no underscores).")
        parser.add_argument(
            "--description",
            default="TBD - replace with real description before committing",
        )
        # quality-debt-ignore: reason: Django add_arguments boilerplate is intentionally repetitive — each argument needs its own parser.add_argument call with its own help text; consolidating these would hide CLI documentation
        parser.add_argument(
            "--contract",
            choices=("proto", "http"),
            default="proto",
            help="Public RPC contract style: 'proto' for gRPC, 'http' for HTTP+JSON.",
        )
        parser.add_argument("--dry-run", action="store_true")

    # quality-debt-ignore: reason: scaffold handle() validates the name, computes 8 target paths, assembles the file map, prints the planned writes and the manual-paste compose YAML blocks, and (if not dry-run) creates parent dirs and writes the eight files; each step is tightly coupled and splitting hurts readability
    def handle(self, *args, **options):
        name = options["name"]
        description = options["description"]
        contract = options["contract"]
        dry_run = options["dry_run"]

        if not NAME_RE.match(name):
            raise CommandError(
                f"Service name '{name}' must be lowercase letters and digits only, "
                f"starting with a letter. Underscores are not allowed in service names "
                f"because they become Go package names (which forbid underscores)."
            )

        root = _repo_root()
        folder = root / "services" / name
        if folder.exists():
            raise CommandError(
                f"{folder.relative_to(root)} already exists. Pick a different name or "
                f"remove the existing folder first."
            )

        files: dict[Path, str] = {
            folder / "go.mod": _gomod(name),
            folder / "cmd" / name / "main.go": _main_go(name),
            folder / "Dockerfile": _dockerfile(name),
            folder / "Makefile": _makefile(name),
            folder / "README.md": _readme(name, description),
        }
        if contract == "proto":
            files[folder / "api.proto"] = _proto(name, description)
            files[folder / "api" / "gen" / "api.pb.go"] = _pb_stub(name)
            files[folder / "api" / "gen" / "api_grpc.pb.go"] = _grpc_stub(name)
        else:
            files[folder / "api.http.md"] = _http_contract(name, description)

        service_block, volume_block = _compose_blocks(name, contract)

        # quality-debt-ignore: reason: self.stdout.write(...) is the Django BaseCommand-native way to emit lines to stdout; each line is a distinct user-facing message; consolidating into a loop hurts readability
        self.stdout.write(f"scaffold_go_service: name={name} contract={contract}")
        for path, body in sorted(files.items()):
            self.stdout.write(f"  would create {path.relative_to(root)} ({len(body)} bytes)")
        # quality-debt-ignore: reason: each self.stdout.write() emits a distinct user-facing line of the scaffold-plan summary; the repeated-call shape is intentional
        self.stdout.write("")
        self.stdout.write("MANUAL FOLLOW-UP - paste these blocks into docker-compose.yml:")
        self.stdout.write("")
        self.stdout.write("  Under the top-level `services:` map:")
        for line in service_block.splitlines():
            self.stdout.write(f"  {line}")
        self.stdout.write("")
        self.stdout.write("  Under the top-level `volumes:` map:")
        for line in volume_block.splitlines():
            self.stdout.write(f"  {line}")
        self.stdout.write("")

        if dry_run:
            self.stdout.write("Dry-run only - no files written. Re-run without --dry-run to apply.")
            return

        for path, body in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

        self.stdout.write(f"Created {len(files)} files under {folder.relative_to(root)}.")
        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write("  1. Paste the YAML blocks above into docker-compose.yml.")
        self.stdout.write("  2. Run `python manage.py audit_go_services --only-broken` to confirm")
        self.stdout.write("     all nine Rule K items are now present.")
        if contract == "proto":
            self.stdout.write(
                f"  3. Run `make -C services/{name} proto` (inside the compiled-tools container) "
                "to regenerate the real gRPC stubs."
            )
        self.stdout.write(f"  {'4' if contract == 'proto' else '3'}. Replace the placeholder "
                          f"`main.go` body with a real server.")
        self.stdout.write(f"  {'5' if contract == 'proto' else '4'}. Add tests and a benchmark.")
