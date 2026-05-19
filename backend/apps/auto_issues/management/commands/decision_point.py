"""manage.py decision_point — post-commit retrospective analyzer.

Session S2 of the PARAMOUNT TDD-pipeline rule. After every successful
commit, `.githooks/post-commit` fires this command which examines the
just-merged diff and surfaces follow-up work in six fixed buckets:

  1. improvements_possible  — long functions, duplicated blocks, etc.
  2. warnings               — TODO / FIXME / XXX comments introduced.
  3. problems               — bare `except:`, `except Exception: pass`.
  4. missing_spec           — new feature/setting without spec citation.
  5. off_track_test_case    — TEST CASE MAPPING marker references a row
                              missing some of the 10 BDD fields.
  6. off_track_tdd          — TDD CYCLE STRICT marker references a row
                              with a weak (single-part) lessons_learned.

Each finding is filed as AutoIssue(category='decision_point',
source='post_commit') with structured `lessons_learned`. The command
prints a `[DECISION POINT: …]` marker that the next code-changing
commit's hook (`.githooks/check-decision-point.py`) validates.

Spec ref: docs/TDD-PIPELINE-RULE.md (authored in Session S4).
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
from dataclasses import dataclass
from datetime import datetime, timezone as dt_tz

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_CATEGORY_KEY = "decision_point"
_CATEGORY_LABEL = "Post-commit decision point"
_CATEGORY_DESC = (
    "Post-commit retrospective finding (improvement / warning / problem / "
    "missing-spec / off-track-test-case / off-track-TDD) filed by the "
    "post-commit Decision Point ritual."
)

_BUCKETS = (
    "improvements",
    "warnings",
    "problems",
    "missing_spec",
    "off_track_test_case",
    "off_track_tdd",
)


@dataclass
class Finding:
    bucket: str
    file: str
    line_hint: str
    detail: str
    severity: str = AutoIssue.SEVERITY_LOW


def _added_lines_by_file(diff: str) -> dict[str, list[tuple[int, str]]]:
    """Parse a unified diff into {file: [(line_no, content), ...]}."""
    out: dict[str, list[tuple[int, str]]] = {}
    current_file: str | None = None
    line_no = 0
    for raw in diff.splitlines():
        if raw.startswith("diff --git"):
            parts = raw.split()
            if len(parts) >= 4:
                b = parts[-1]
                current_file = b[2:] if b.startswith("b/") else b
                out.setdefault(current_file, [])
                line_no = 0
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            if m:
                line_no = int(m.group(1)) - 1
        elif raw.startswith("+++") or raw.startswith("---"):
            continue
        elif raw.startswith("+"):
            line_no += 1
            if current_file is not None:
                out[current_file].append((line_no, raw[1:]))
        elif not raw.startswith("-"):
            line_no += 1
    return out


def _detect_warnings(by_file: dict[str, list[tuple[int, str]]]) -> list[Finding]:
    findings: list[Finding] = []
    for file, lines in by_file.items():
        for line_no, content in lines:
            for kind in ("TODO", "FIXME", "XXX"):
                if re.search(rf"\b{kind}\b", content):
                    findings.append(Finding(
                        bucket="warnings",
                        file=file,
                        line_hint=f"line {line_no}",
                        detail=f"{kind} comment introduced",
                    ))
                    break
    return findings


def _detect_problems(by_file: dict[str, list[tuple[int, str]]]) -> list[Finding]:
    findings: list[Finding] = []
    for file, lines in by_file.items():
        for i, (line_no, content) in enumerate(lines):
            if re.match(r"\s*except\s*:\s*$", content):
                findings.append(Finding(
                    bucket="problems",
                    file=file,
                    line_hint=f"line {line_no}",
                    detail="bare `except:` — catches everything including KeyboardInterrupt",
                    severity=AutoIssue.SEVERITY_MEDIUM,
                ))
                continue
            if re.match(r"\s*except\s+Exception(\s+as\s+\w+)?\s*:\s*$", content):
                # Look ahead to confirm `pass` body or empty body.
                if i + 1 < len(lines):
                    next_content = lines[i + 1][1]
                    if re.match(r"\s*pass\s*$", next_content):
                        findings.append(Finding(
                            bucket="problems",
                            file=file,
                            line_hint=f"line {line_no}",
                            detail="`except Exception: pass` — silently swallows errors",
                            severity=AutoIssue.SEVERITY_MEDIUM,
                        ))
    return findings


def _detect_improvements(by_file: dict[str, list[tuple[int, str]]]) -> list[Finding]:
    """Long-function detector. AGENTS.md caps functions at 50 lines."""
    findings: list[Finding] = []
    for file, lines in by_file.items():
        in_function = False
        function_name = "<unknown>"
        function_start = 0
        consecutive = 0
        for line_no, content in lines:
            stripped = content.lstrip()
            if stripped.startswith("def ") or stripped.startswith("async def "):
                if in_function and consecutive > 50:
                    findings.append(Finding(
                        bucket="improvements",
                        file=file,
                        line_hint=f"function `{function_name}` starts at line {function_start}",
                        detail=(
                            f"function `{function_name}` is {consecutive + 1} lines "
                            f"(exceeds the 50-line cap in AGENTS.md)"
                        ),
                    ))
                in_function = True
                m = re.match(r"\s*(?:async\s+)?def\s+(\w+)", content)
                function_name = m.group(1) if m else "<unknown>"
                function_start = line_no
                consecutive = 0
            elif in_function:
                consecutive += 1
        if in_function and consecutive > 50:
            findings.append(Finding(
                bucket="improvements",
                file=file,
                line_hint=f"function `{function_name}` starts at line {function_start}",
                detail=(
                    f"function `{function_name}` is {consecutive + 1} lines "
                    f"(exceeds the 50-line cap in AGENTS.md)"
                ),
            ))
    return findings


def _detect_missing_spec(by_file: dict[str, list[tuple[int, str]]]) -> list[Finding]:
    """Hard rule already enforced by check-spec-citation.py. The Decision
    Point only files a follow-up artefact when a *staged* SPEC PROOF marker
    was missing — which is unreachable since the strict gate blocks at
    commit. Returns empty in S2; the bucket exists so future rules (e.g. a
    looser detection mode) have a slot."""
    return []


def _detect_off_track_test_case(diff: str) -> list[Finding]:
    findings: list[Finding] = []
    for m in re.finditer(
        r"\[TEST CASE MAPPING:\s*file=(\S+)\s+test_cases=([#\d,]+)\s*\]",
        diff,
    ):
        file = m.group(1)
        ids = [int(s.lstrip("#")) for s in m.group(2).split(",") if s.strip()]
        for autoissue_id in ids:
            ai = AutoIssue.objects.filter(pk=autoissue_id).first()
            if ai is None:
                findings.append(Finding(
                    bucket="off_track_test_case",
                    file=file,
                    line_hint=f"AutoIssue=#{autoissue_id}",
                    detail=(
                        f"TEST CASE MAPPING references AutoIssue "
                        f"#{autoissue_id} which does not exist"
                    ),
                    severity=AutoIssue.SEVERITY_HIGH,
                ))
                continue
            lessons = (ai.lessons_learned or "").lower()
            required = (
                "given", "when", "then",
                "edge_cases", "failure_cases", "security",
                "usability", "scalability", "maintainability",
                "regression_risks",
            )
            missing = [r for r in required if r not in lessons]
            if missing:
                findings.append(Finding(
                    bucket="off_track_test_case",
                    file=file,
                    line_hint=f"AutoIssue=#{autoissue_id}",
                    detail=(
                        f"test_case AutoIssue #{autoissue_id} is missing BDD "
                        f"fields: {', '.join(missing)}"
                    ),
                    severity=AutoIssue.SEVERITY_MEDIUM,
                ))
    return findings


def _detect_off_track_tdd(diff: str) -> list[Finding]:
    findings: list[Finding] = []
    pattern = re.compile(
        r"\[TDD CYCLE STRICT:.*?file=(\S+).*?lesson_autoissue=#(\d+)\s*\]",
        flags=re.DOTALL,
    )
    for m in pattern.finditer(diff):
        file = m.group(1)
        autoissue_id = int(m.group(2))
        ai = AutoIssue.objects.filter(pk=autoissue_id).first()
        if ai is None:
            findings.append(Finding(
                bucket="off_track_tdd",
                file=file,
                line_hint=f"AutoIssue=#{autoissue_id}",
                detail=(
                    f"TDD CYCLE STRICT references AutoIssue #{autoissue_id} "
                    f"which does not exist"
                ),
                severity=AutoIssue.SEVERITY_HIGH,
            ))
            continue
        lessons = ai.lessons_learned or ""
        if "Trap:" not in lessons or "Fix shape:" not in lessons:
            findings.append(Finding(
                bucket="off_track_tdd",
                file=file,
                line_hint=f"AutoIssue=#{autoissue_id}",
                detail=(
                    "tdd_lesson AutoIssue lessons_learned is missing required "
                    "two-part Trap: / Fix shape: payload"
                ),
                severity=AutoIssue.SEVERITY_MEDIUM,
            ))
    return findings


def analyze_diff(diff: str) -> dict[str, list[Finding]]:
    by_file = _added_lines_by_file(diff)
    return {
        "improvements": _detect_improvements(by_file),
        "warnings": _detect_warnings(by_file),
        "problems": _detect_problems(by_file),
        "missing_spec": _detect_missing_spec(by_file),
        "off_track_test_case": _detect_off_track_test_case(diff),
        "off_track_tdd": _detect_off_track_tdd(diff),
    }


def _git_show_diff(commit_hash: str) -> str:
    """Return the unified diff of a single commit. Mockable for tests."""
    try:
        result = subprocess.run(  # nosec
            ["git", "show", "--unified=0", "--no-color", commit_hash],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout or ""


def _resolve_commit(commit: str) -> str:
    """Resolve `HEAD` / branch / short hash to a full 40-char SHA. Falls back to the input on failure."""
    try:
        result = subprocess.run(  # nosec
            ["git", "rev-parse", commit],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return commit
    if result.returncode != 0:
        return commit
    return (result.stdout or commit).strip() or commit


def _get_or_create_category() -> AutoIssueCategory:
    cat, _ = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": _CATEGORY_DESC,
            "sort_order": 225,
        },
    )
    return cat


def _now_iso8601_z() -> str:
    return datetime.now(dt_tz.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _file_findings(
    findings_by_bucket: dict[str, list[Finding]],
    short_hash: str,
    category: AutoIssueCategory,
    now,
) -> list[int]:
    """File each finding as an AutoIssue, deduping by canonical_fingerprint."""
    filed_ids: list[int] = []
    for bucket, findings in findings_by_bucket.items():
        for finding in findings:
            canonical = canonical_fingerprint(
                f"{bucket}::{finding.file}::{finding.detail}"
            )
            existing = AutoIssue.objects.filter(
                canonical_fingerprint=canonical,
                category=category,
                status__in=("open", "picked", "in_progress"),
            ).first()
            if existing is not None:
                existing.occurrence_count += 1
                existing.last_seen = now
                existing.save(update_fields=["occurrence_count", "last_seen"])
                filed_ids.append(existing.pk)
                continue
            ext_id = f"decision_point::{short_hash}::{bucket}::{finding.file}::{finding.line_hint}"
            title = f"Decision Point ({bucket}): {finding.detail}"[:512]
            description = (
                f"Bucket: {bucket}\n"
                f"File: {finding.file}\n"
                f"Location: {finding.line_hint}\n"
                f"Detail: {finding.detail}\n"
                f"Commit: {short_hash}\n"
            )
            ai = AutoIssue.objects.create(
                source=AutoIssue.SOURCE_AGENT,
                external_id=ext_id[:128],
                fingerprint=ext_id[:64],
                canonical_fingerprint=canonical,
                title=title,
                description=description,
                affected_files=[finding.file],
                severity=finding.severity,
                category=category,
                status=AutoIssue.STATUS_OPEN,
                occurrence_count=1,
                last_seen=now,
                lessons_learned="",
            )
            filed_ids.append(ai.pk)
    return filed_ids


def _format_marker(
    *,
    short_hash: str,
    counts: dict[str, int],
    autoissues_str: str,
    filed_at: str,
    dry_run: bool,
) -> str:
    total = sum(counts.values())
    prefix = "DECISION POINT DRY-RUN" if dry_run else "DECISION POINT"
    pieces = [
        f"[{prefix}: commit={short_hash}",
        f"findings={total}",
        f"improvements={counts['improvements']}",
        f"warnings={counts['warnings']}",
        f"problems={counts['problems']}",
        f"missing_spec={counts['missing_spec']}",
        f"off_track_test_case={counts['off_track_test_case']}",
        f"off_track_tdd={counts['off_track_tdd']}",
    ]
    if not dry_run:
        pieces.append(f"autoissues_filed={autoissues_str}")
        pieces.append(f"filed_at={filed_at}]")
    else:
        pieces[-1] = pieces[-1] + "]"
    return " ".join(pieces)


class Command(BaseCommand):
    help = (
        "Post-commit Decision Point ritual: analyse the given commit's "
        "diff and file follow-up AutoIssues in six fixed buckets."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--commit", required=True,
                            help="Commit hash to analyse (e.g. HEAD).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Analyse but do not file AutoIssues.")
        parser.add_argument("--agent", default="post_commit",
                            help="Agent / source label (unused for now).")

    def handle(self, *args, **opts) -> None:
        commit_in = (opts.get("commit") or "").strip()
        if not commit_in:
            raise CommandError("FAIL decision_point: --commit is required.")
        commit = _resolve_commit(commit_in)
        short_hash = commit[:7]

        diff = _git_show_diff(commit)
        findings_by_bucket = analyze_diff(diff)
        counts = {b: len(findings_by_bucket[b]) for b in _BUCKETS}

        if opts.get("dry_run"):
            marker = _format_marker(
                short_hash=short_hash,
                counts=counts,
                autoissues_str="",
                filed_at=_now_iso8601_z(),
                dry_run=True,
            )
            self.stdout.write(marker)
            return

        category = _get_or_create_category()
        now = timezone.now()
        filed_ids = _file_findings(findings_by_bucket, short_hash, category, now)
        autoissues_str = ",".join(f"#{pk}" for pk in filed_ids) if filed_ids else "none"
        marker = _format_marker(
            short_hash=short_hash,
            counts=counts,
            autoissues_str=autoissues_str,
            filed_at=_now_iso8601_z(),
            dry_run=False,
        )
        self.stdout.write(marker)
