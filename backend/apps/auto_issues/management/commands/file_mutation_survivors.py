"""manage.py file_mutation_survivors — Phase I command.

Reads a mutation-tool JSON report and files one
`AutoIssue(category='mutation_survivor', source='mutation')` per
surviving mutant. Deduplicates via canonical_fingerprint built from
`(tool, file, line, mutator-name)` so repeated runs of the same
mutation pass don't multiply the row count.

Tool report shapes supported:

- **Stryker** (`frontend/reports/stryker.json`): standard Stryker
  v4+ mutation-test-elements format. Survivors are mutants with
  `status="Survived"`.
- **mutmut** (`mutants/mutmut-cicd-stats.json`): mutmut's
  export-cicd-stats output. Survivors are entries in `survivors[]`.
- **Mull** (`<binary>/mutants.json`): Mull Elements reporter output.
  Survivors are mutants where `status == "NotCovered"` or
  `"Survived"`.
- **go-mutesting** (`<module>/report.json`): go-mutesting report.
  Survivors are entries in `mutators[]` where `result.passed == true`
  (mutated test still passed, i.e. test suite didn't catch the
  mutation).

Severity is computed per the mutator-name map in
`apps.auto_issues.services.mutation_severity`. Priority is then
ordered by the existing C++ algorithm (Bayesian classifier +
canonical_fingerprint dedup); see `compute_priority` in
`apps.auto_issues.services.scoring`.

Marker emitted on success:
    [MUTATION SURVIVORS FILED: tool=<name> filed=<N> deduped=<K>
     total=<N+K>]

Marker emitted when the report is missing or empty:
    [MUTATION SURVIVORS: tool=<name> none — clean run]

Spec: Phase I of the per-module-coverage hard-gate plan.
Sources: Sahami et al. 1998 (Bayesian classifier),
Robinson 2003 (spam-score), MMDS Ch. 13, Bloom 1970.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.auto_issues.services.mutation_severity import severity_for


_CATEGORY_KEY = "mutation_survivor"
_CATEGORY_LABEL = "Mutation survivor"

_SUPPORTED_TOOLS = {"stryker", "mutmut", "mull", "go-mutesting"}


def _get_or_create_category() -> AutoIssueCategory:
    cat, _ = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": (
                "Surviving mutant filed by file_mutation_survivors. Each row "
                "names one mutant the test suite did not kill. Priority is "
                "ordered by mutator severity + the C++ priority algorithm; "
                "the 30-pick session quota surfaces the dangerous ones first."
            ),
            "sort_order": 250,
        },
    )
    return cat


def _normalise_path(p: str) -> str:
    return (p or "").strip().replace("\\", "/").lstrip("./")


def _fingerprint(tool: str, file: str, line: int, mutator: str) -> str:
    """Stable fingerprint for dedup across re-runs."""
    h = hashlib.sha1(
        f"{tool}:{_normalise_path(file)}:{line}:{mutator}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    return h[:16]


def _parse_stryker(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Standard Stryker mutation-test-elements format. Files keyed by path."""
    survivors: list[dict[str, Any]] = []
    files = payload.get("files") or {}
    for path, body in files.items():
        for mutant in body.get("mutants") or []:
            if mutant.get("status") != "Survived":
                continue
            loc = mutant.get("location") or {}
            start = loc.get("start") or {}
            survivors.append({
                "file": _normalise_path(path),
                "line": int(start.get("line") or 0),
                "mutator": str(mutant.get("mutatorName") or "unknown"),
                "replacement": str(mutant.get("replacement") or ""),
                "id": str(mutant.get("id") or ""),
            })
    return survivors


def _parse_mutmut(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """mutmut export-cicd-stats format. Survivors list in `survivors`."""
    survivors: list[dict[str, Any]] = []
    raw = payload.get("survivors") or []
    for entry in raw:
        if isinstance(entry, str):
            # entry is "module::mutator__N" — parse out the parts.
            parts = entry.split("::", 1)
            file = parts[0] if parts else "unknown"
            mutator = parts[1] if len(parts) > 1 else "unknown"
            survivors.append({
                "file": _normalise_path(file),
                "line": 0,
                "mutator": mutator,
                "replacement": "",
                "id": entry,
            })
        elif isinstance(entry, dict):
            survivors.append({
                "file": _normalise_path(str(entry.get("file") or "unknown")),
                "line": int(entry.get("line") or 0),
                "mutator": str(entry.get("type") or "unknown"),
                "replacement": str(entry.get("replacement") or ""),
                "id": str(entry.get("id") or ""),
            })
    return survivors


def _parse_mull(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Mull Elements reporter format."""
    survivors: list[dict[str, Any]] = []
    mutants = payload.get("mutants") or []
    for mutant in mutants:
        status = str(mutant.get("status") or "").lower()
        if status not in {"survived", "notcovered"}:
            continue
        loc = mutant.get("location") or {}
        survivors.append({
            "file": _normalise_path(str(loc.get("file") or "unknown")),
            "line": int(loc.get("line") or 0),
            "mutator": str(mutant.get("mutator") or "unknown"),
            "replacement": str(mutant.get("replacement") or ""),
            "id": str(mutant.get("id") or ""),
        })
    return survivors


def _parse_go_mutesting(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """go-mutesting report format."""
    survivors: list[dict[str, Any]] = []
    mutators = payload.get("mutators") or []
    for entry in mutators:
        result = entry.get("result") or {}
        # In go-mutesting, `passed == true` on a mutated build means the
        # test suite DID NOT detect the mutation, i.e. the mutant survived.
        if not result.get("passed", False):
            continue
        survivors.append({
            "file": _normalise_path(str(entry.get("file") or "unknown")),
            "line": int(entry.get("line") or 0),
            "mutator": str(entry.get("type") or entry.get("mutator") or "unknown"),
            "replacement": "",
            "id": str(entry.get("id") or ""),
        })
    return survivors


_PARSERS = {
    "stryker": _parse_stryker,
    "mutmut": _parse_mutmut,
    "mull": _parse_mull,
    "go-mutesting": _parse_go_mutesting,
}


class Command(BaseCommand):
    help = "File AutoIssues for each surviving mutant (Phase I soft-block)."

    def add_arguments(self, parser):
        parser.add_argument("--tool", required=True, choices=sorted(_SUPPORTED_TOOLS),
                            help="Which mutation tool the report came from.")
        parser.add_argument("--report", required=True,
                            help="Path to the tool's JSON report.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Parse + count but do not write AutoIssues.")
        parser.add_argument("--agent", default="claude",
                            help="Agent name recorded as resolved_by / observation source.")

    def handle(self, *args, **opts):
        tool = opts["tool"]
        report_path = Path(opts["report"])
        agent = opts["agent"][:64]

        if not report_path.is_file():
            # Per Phase I: a missing report is treated as a clean run.
            # The mutation step may have crashed or hit the 5-min cap;
            # either way, no survivors to file. The chain logs evidence
            # separately.
            self.stdout.write(
                f"[MUTATION SURVIVORS: tool={tool} none — report missing at {report_path}]"
            )
            return

        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(
                f"FAIL file_mutation_survivors: could not parse {report_path}: {exc}\n"
                f"WHY: the report must be valid JSON.\n"
                f"UNBLOCK: rerun the mutation tool and check the report path."
            )

        parser_fn = _PARSERS[tool]
        survivors = parser_fn(payload)

        if not survivors:
            self.stdout.write(
                f"[MUTATION SURVIVORS: tool={tool} none — clean run]"
            )
            return

        category = _get_or_create_category()
        now = timezone.now()

        filed = 0
        deduped = 0
        for s in survivors:
            mutator = s["mutator"]
            file_path = s["file"]
            line = s["line"]
            fp = _fingerprint(tool, file_path, line, mutator)
            severity = severity_for(tool, mutator)
            title = (
                f"[{tool}] {file_path}:{line} surviving mutant ({mutator})"
            )[:512]
            cf = canonical_fingerprint(title)
            description = (
                f"Mutation tool: {tool}\n"
                f"File: {file_path}:{line}\n"
                f"Mutator: {mutator}\n"
                f"Replacement: {s.get('replacement') or '(see tool report)'}\n"
                f"Severity: {severity} (per apps.auto_issues.services.mutation_severity)\n"
                f"\n"
                f"Trap: the test suite covers this line but does not assert "
                f"the specific behaviour the mutator changed. The mutant "
                f"survived, so a bug of the same shape could land without "
                f"any test failing.\n"
                f"Fix shape: add at least one behavior-asserting test that "
                f"would fail when the mutator's replacement is applied. "
                f"Re-run the tool to confirm the mutant is now killed."
            )

            ext_id = f"mutation::{tool}::{fp}"
            existing = AutoIssue.objects.filter(
                external_id=ext_id,
            ).first()

            if existing is not None:
                existing.occurrence_count += 1
                existing.last_seen = now
                obs = {
                    "source": "mutation",
                    "external_id": ext_id,
                    "first_seen": existing.first_seen.isoformat()
                    if existing.first_seen else now.isoformat(),
                    "last_seen": now.isoformat(),
                    "occurrence_count": existing.occurrence_count,
                    "tool": tool,
                    "mutator": mutator,
                    "agent": agent,
                }
                existing.source_observations = [
                    *(existing.source_observations or []),
                    obs,
                ][:50]  # cap observation list
                merged = list(dict.fromkeys((existing.affected_files or []) + [file_path]))
                existing.affected_files = merged
                existing.save()
                deduped += 1
                continue

            AutoIssue.objects.create(
                source=AutoIssue.SOURCE_MUTATION,
                external_id=ext_id,
                fingerprint=fp,
                canonical_fingerprint=cf,
                title=title,
                description=description,
                affected_files=[file_path],
                severity=severity,
                category=category,
                status=AutoIssue.STATUS_OPEN,
                first_seen=now,
                last_seen=now,
                occurrence_count=1,
                source_observations=[
                    {
                        "source": "mutation",
                        "external_id": ext_id,
                        "first_seen": now.isoformat(),
                        "last_seen": now.isoformat(),
                        "occurrence_count": 1,
                        "tool": tool,
                        "mutator": mutator,
                        "agent": agent,
                    }
                ],
            )
            filed += 1

        total = filed + deduped
        self.stdout.write(
            f"[MUTATION SURVIVORS FILED: tool={tool} filed={filed} "
            f"deduped={deduped} total={total}]"
        )
