"""Register the canonical Avro schemas with the schemard sidecar.

Reads every ``*.avsc`` file under services/sidecars/schemas/ and registers it
with schemard, using the file stem as the subject (e.g. ``auto_issue.v1``).
This is the "wire it up" step for Avro: after this runs, schemard knows the
versioned shape of every domain event, and snapshotd's CheckCompat call has a
prior version to evaluate candidates against.

Idempotent: re-registering an identical schema just adds a new version row.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

_REL = Path("services") / "sidecars" / "schemas"


def _schemas_dir() -> Path:
    """Locate services/sidecars/schemas across environments.

    The schemas are the shared Go<->Python contract; they live next to the Go
    schemard service. The backend container mounts the whole repo at /repo,
    while host/compiled-tools runs see it under the repo root. Check, in order:
    an explicit env override, the /repo mount, then the BASE_DIR-relative path.
    """
    override = os.environ.get("XF_AVRO_SCHEMAS_DIR")
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates.append(Path("/repo") / _REL)
    candidates.append(Path(settings.BASE_DIR).resolve().parent / _REL)
    for c in candidates:
        if c.is_dir():
            return c
    # Fall back to the repo-root-relative path for the error message.
    return candidates[-1]


class Command(BaseCommand):
    help = "Register canonical Avro schemas (services/sidecars/schemas/*.avsc) with schemard."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List the schemas that would be registered without contacting schemard.",
        )
        parser.add_argument(
            "--require-backward-compat",
            action="store_true",
            help="Reject a schema that is not backward-compatible with its prior version.",
        )

    def handle(self, *args, **options) -> None:
        schemas_dir = _schemas_dir()
        avsc_files = sorted(schemas_dir.glob("*.avsc"))
        if not avsc_files:
            raise CommandError(f"No .avsc schemas found under {schemas_dir}")

        if options["dry_run"]:
            for path in avsc_files:
                self._validate_json(path)
                self.stdout.write(f"  would register: {path.stem}")
            self.stdout.write(f"[AVRO SCHEMAS: dry-run {len(avsc_files)} schema(s)]")
            return

        # Imported lazily so --dry-run works without the sidecar stubs present.
        from apps.auto_issues._sidecars.schemard_client import SchemardClient

        client = SchemardClient()
        registered = []
        for path in avsc_files:
            schema_json = self._validate_json(path)
            version = client.register(
                subject=path.stem,
                schema_json=schema_json,
                require_backward_compat=options["require_backward_compat"],
            )
            registered.append(f"{version.subject}@v{version.version}")
            self.stdout.write(f"  registered: {version.subject} -> v{version.version}")
        self.stdout.write(
            f"[AVRO SCHEMAS REGISTERED: {len(registered)} -> {', '.join(registered)}]"
        )

    def _validate_json(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise CommandError(f"{path.name} is not valid JSON: {exc}") from exc
        return text
