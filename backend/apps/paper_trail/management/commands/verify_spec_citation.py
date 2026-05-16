"""manage.py verify_spec_citation — confirm docs/specs/<id>.md cites a known reference."""

from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.paper_trail.services import lesson_index as svc


_SPEC_CITED_RE = re.compile(
    r"\[SPEC CITED:\s*feature=([^\s]+)\s+kind=(\w+)\s+id=(\S+)\s+verified_at=([^\]]+)\]"
)


class Command(BaseCommand):
    help = "Verify a docs/specs/<feature>.md cites at least one known reference."

    def add_arguments(self, parser):
        parser.add_argument("--feature-id", required=True)
        parser.add_argument("--spec-path", default="",
                            help="Override the default docs/specs/<id>.md path.")

    def handle(self, *args, **opts):
        feature = opts["feature_id"]
        path = (
            Path(opts["spec_path"])
            if opts["spec_path"]
            else Path("/repo/docs/specs") / f"{feature}.md"
        )
        if not path.is_file():
            raise CommandError(
                f"FAIL verify_spec_citation: {path} does not exist. "
                f"Create docs/specs/{feature}.md and cite at least one "
                f"patent, DOI, RFC, or stable URL before implementing."
            )
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = _SPEC_CITED_RE.findall(text)
        if not matches:
            raise CommandError(
                f"FAIL verify_spec_citation: {path} contains no [SPEC CITED:] "
                f"marker. Add at least one citation in the form "
                f"`[SPEC CITED: feature={feature} kind=doi id=... verified_at=...]` "
                f"and run `manage.py cite_spec` to register it."
            )
        unresolved = [
            (kind, ref_id) for (_, kind, ref_id, _) in matches
            if svc.cite_get(f"{kind[0]}:{ref_id}") is None
            and svc.cite_get(f"{kind}:{ref_id}") is None
        ]
        if unresolved:
            joined = ", ".join(f"{k}:{i}" for k, i in unresolved)
            raise CommandError(
                f"FAIL verify_spec_citation: {len(unresolved)} citation(s) in "
                f"{path} have no CitationCache entry: {joined}. Run "
                f"`manage.py cite_spec --key <kind>:<id> ...` for each."
            )
        self.stdout.write(
            f"[SPEC CITATION VERIFIED: feature={feature} citations={len(matches)}]"
        )
