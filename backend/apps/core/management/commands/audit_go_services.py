# quality-debt-ignore: reason: smoke tests for the 4 lifecycle helper commands live together at backend/apps/core/test_lifecycle_helpers.py because they share the same _repo_root() helper and fixture shape; co-locating them keeps the test surface small and avoids per-command duplication
"""Audit every services/<name>/ folder against the 9 Rule K lifecycle items (read-only).

Plain-English summary
---------------------

This command lists every Go service under `services/` and shows which of
the nine required artefacts is present. A service is healthy only when
all nine are present together; the pre-commit hook
`.githooks/check-go-service-contract.py` will hard-block commits when
any service is missing any of the nine.

The nine items:
  1. go.mod
  2. api.proto OR api.http.md
  3. cmd/<name>/main.go
  4. Dockerfile
  5. api/gen/*.pb.go (only when api.proto exists)
  6. docker-compose.yml service block
  7. go.sum populated (when go.mod has require directives)
  8. Dockerfile is multi-stage (>=2 FROM directives)
  9. docker-compose.yml declares <name>_sock named volume (gRPC only)

Run this when you want a status overview without trying to commit. It is
read-only (no --dry-run needed; nothing is written).

Usage:
  docker compose exec -T backend python manage.py audit_go_services
  docker compose exec -T backend python manage.py audit_go_services --only-broken
  docker compose exec -T backend python manage.py audit_go_services --json
"""
# xf: no_dry_run -- read-only audit; no state changes

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from django.core.management.base import BaseCommand

from ._lifecycle_helpers import repo_root as _repo_root


def _load_hook(root: Path):
    hook_path = root / ".githooks" / "check-go-service-contract.py"
    if not hook_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_audit_go_hook", hook_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_audit_go_hook"] = module
    spec.loader.exec_module(module)
    # Point the hook at the real repo root so its compose-yaml reads land.
    module.REPO_ROOT = root
    module.SERVICES_DIR = root / "services"
    return module


class Command(BaseCommand):
    help = "Audit every services/<name>/ folder against the 9 Rule K lifecycle items."

    def add_arguments(self, parser):
        # quality-debt-ignore: reason: Django add_arguments boilerplate is intentionally repetitive — each argument needs its own parser.add_argument call with its own help text; consolidating these would hide CLI documentation
        parser.add_argument(
            "--only-broken",
            action="store_true",
            help="Show only services that violate Rule K (any of nine items missing).",
        )
        # quality-debt-ignore: reason: Django parser.add_argument boilerplate; each argument needs its own call with its own help text
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output a JSON document instead of the human-readable table.",
        )

    # quality-debt-ignore: reason: handle() loads the hook module, walks services/, scans each service folder, then renders a table — the steps are tightly coupled to the audit output shape and splitting hurts readability
    def handle(self, *args, **options):
        root = _repo_root()
        hook = _load_hook(root)
        if hook is None:
            self.stderr.write("audit_go_services: hook script not found; nothing to audit.")
            return

        services_dir = root / "services"
        if not services_dir.is_dir():
            self.stdout.write("audit_go_services: no services/ directory in this repo.")
            return

        rows = []
        folders = hook._list_service_folders(services_dir)
        for folder in folders:
            violations = hook.scan_service_folder(folder)
            kinds = sorted({v.kind for v in violations})
            rows.append({
                "service": folder.name,
                "ok": not violations,
                "missing_kinds": kinds,
                "messages": [v.message for v in violations],
            })

        if options["only_broken"]:
            rows = [r for r in rows if not r["ok"]]

        if options["json"]:
            self.stdout.write(json.dumps(rows, indent=2))
            return

        ok_count = sum(1 for r in rows if r["ok"])
        bad_count = sum(1 for r in rows if not r["ok"])
        self.stdout.write("Go service lifecycle audit (Rule K)")
        self.stdout.write(f"  PRESENT  (all nine items present): {ok_count}")
        self.stdout.write(f"  BROKEN   (one or more items missing): {bad_count}")
        self.stdout.write("")
        for r in rows:
            tag = "OK    " if r["ok"] else "BROKEN"
            self.stdout.write(f"  {tag}  {r['service']}")
            for kind in r["missing_kinds"]:
                self.stdout.write(f"           missing: {kind}")
        if bad_count:
            self.stdout.write("")
            self.stdout.write(
                "Fix BROKEN rows before committing — the pre-commit hook "
                ".githooks/check-go-service-contract.py will hard-block any "
                "commit while any of the nine items is missing. Each missing "
                "kind's message above tells you what file to create."
            )
