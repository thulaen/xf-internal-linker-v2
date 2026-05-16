"""manage.py migrate_handoff_deferrals — backfill from AGENT-HANDOFF.md prose.

Parses every entry under each handoff section that names deferred work
("What has issues or errors:" or "What was deferred:") and creates a
PaperTrailEntry row per item. Idempotent — re-running creates 0 rows.

Category is inferred from keyword heuristics over the entry body.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.utils import timezone as djtz

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import dedup as dedup_service
from apps.paper_trail.services.priority import compute_priority_score


# Entry header regex: "# 2026-05-15 15:56 - Claude Opus 4.7 - Title"
_ENTRY_HEADER_RE = re.compile(
    r"^#\s*(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2})\s*-\s*"
    r"(?P<agent>[^-\n]+?)\s*-\s*(?P<title>.+)$",
    re.MULTILINE,
)
_AUTOISSUE_REF_RE = re.compile(r"#(\d+)")
_DEFERRED_SECTION_RE = re.compile(
    r"What\s+(?:has\s+issues\s+or\s+errors|was\s+deferred)[:\s]",
    re.IGNORECASE,
)
# Section terminators — the section ends when we hit "Verification:", "Tech-debt", "---", or the next # header.
_SECTION_TERMINATORS = ("Verification:", "Tech-debt delta:", "---", "Next session")


_CATEGORY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("cve", PaperTrailEntry.CATEGORY_CVE_UPGRADE),
    ("pip-audit", PaperTrailEntry.CATEGORY_CVE_UPGRADE),
    ("vulnerab", PaperTrailEntry.CATEGORY_SECURITY),
    ("safety", PaperTrailEntry.CATEGORY_CVE_UPGRADE),
    ("dependency", PaperTrailEntry.CATEGORY_DEPENDENCY_UPGRADE),
    ("ruff", PaperTrailEntry.CATEGORY_RUFF_SWEEP),
    ("lint", PaperTrailEntry.CATEGORY_RUFF_SWEEP),
    ("coverage", PaperTrailEntry.CATEGORY_COVERAGE_GAP),
    ("mull", PaperTrailEntry.CATEGORY_MUTATION_SURVIVOR),
    ("mutmut", PaperTrailEntry.CATEGORY_MUTATION_SURVIVOR),
    ("stryker", PaperTrailEntry.CATEGORY_MUTATION_SURVIVOR),
    ("mutant", PaperTrailEntry.CATEGORY_MUTATION_SURVIVOR),
    ("backup", PaperTrailEntry.CATEGORY_INFRASTRUCTURE),
    ("monitoring", PaperTrailEntry.CATEGORY_INFRASTRUCTURE),
    ("alert", PaperTrailEntry.CATEGORY_INFRASTRUCTURE),
    ("grafana", PaperTrailEntry.CATEGORY_INFRASTRUCTURE),
    ("gpu", PaperTrailEntry.CATEGORY_INFRASTRUCTURE),
    ("docs/", PaperTrailEntry.CATEGORY_DOCUMENTATION),
    ("documentation", PaperTrailEntry.CATEGORY_DOCUMENTATION),
    ("perf", PaperTrailEntry.CATEGORY_PERFORMANCE),
    ("a11y", PaperTrailEntry.CATEGORY_ACCESSIBILITY),
    ("accessibility", PaperTrailEntry.CATEGORY_ACCESSIBILITY),
    ("autoissue", PaperTrailEntry.CATEGORY_AUTOISSUE_DEFERRAL),
    ("tooling", PaperTrailEntry.CATEGORY_TOOLING_GAP),
    ("hook", PaperTrailEntry.CATEGORY_TOOLING_GAP),
    ("refactor", PaperTrailEntry.CATEGORY_REFACTOR),
    ("debt", PaperTrailEntry.CATEGORY_DEBT_REDUCTION),
)


def _infer_category(text: str) -> str:
    lower = text.lower()
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in lower:
            return category
    return PaperTrailEntry.CATEGORY_OTHER


def _parse_handoff(content: str):
    """Yield (header_match, body) tuples for each handoff entry."""
    matches = list(_ENTRY_HEADER_RE.finditer(content))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        yield m, content[m.end():end]


def _extract_deferred_items(body: str) -> list[str]:
    """Return a list of paragraph strings from the deferred section."""
    match = _DEFERRED_SECTION_RE.search(body)
    if not match:
        return []
    section = body[match.end():]
    # Cut at the first terminator.
    cut = len(section)
    for term in _SECTION_TERMINATORS:
        idx = section.find(term)
        if idx != -1:
            cut = min(cut, idx)
    section = section[:cut].strip()
    if not section:
        return []

    items: list[str] = []
    current: list[str] = []
    started = False
    numbered = re.compile(r"^\s*\d+\.\s+")
    bullet = re.compile(r"^\s*[-*]\s+")
    for line in section.splitlines():
        if numbered.match(line) or bullet.match(line):
            if current:
                items.append(" ".join(current).strip())
            current = [numbered.sub("", bullet.sub("", line)).strip()]
            started = True
        elif line.strip() and started:
            # Continuation lines only count once we've seen the first
            # bullet — keeps intro paragraphs out of the item set.
            current.append(line.strip())
        elif not line.strip() and current:
            items.append(" ".join(current).strip())
            current = []
    if current:
        items.append(" ".join(current).strip())

    # Drop very-short items that are just connectors.
    return [it for it in items if len(it) > 40]


def _short_title(item: str, max_len: int = 200) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", item, maxsplit=1)[0]
    return sentence[:max_len]


def _truncate_words(text: str, max_words: int = 1200) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def _ensure_bdd_shape(abstract: str, *, category: str, title: str) -> str:
    """Return `abstract` unchanged if it already contains Given/When/Then;
    otherwise wrap the original text in a synthetic BDD frame so the new
    model-level validator accepts it during bulk-migration of legacy
    handoff prose.
    """
    lowered = abstract.lower()
    if (
        re.search(r"\bgiven\b", lowered)
        and re.search(r"\bwhen\b", lowered)
        and re.search(r"\bthen\b", lowered)
    ):
        return abstract
    return (
        f"Given the prior session deferred this item via narrative prose "
        f"under the `{category}` category, "
        f"When the migrate_handoff_deferrals command bulk-imports the "
        f"deferral into the paper-trail table, "
        f"Then the deferral is searchable, dedupable, and resolvable by "
        f"future agents per the title \"{title[:120]}\".\n\n"
        f"Original prose follows: {abstract}"
    )


class Command(BaseCommand):
    help = "Backfill PaperTrailEntry rows from AGENT-HANDOFF.md prose sections."

    def add_arguments(self, parser):
        parser.add_argument(
            "--handoff-path",
            default="/repo/AGENT-HANDOFF.md",
        )
        parser.add_argument("--from-date", default="2026-05-01")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        path = Path(opts["handoff_path"])
        if not path.is_file():
            self.stderr.write(f"AGENT-HANDOFF.md not found at {path}")
            return
        content = path.read_text(encoding="utf-8", errors="replace")
        cutoff = datetime.strptime(opts["from_date"], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )

        created = 0
        skipped_dupe = 0
        scanned = 0

        for header, body in _parse_handoff(content):
            entry_dt = datetime.strptime(
                f"{header['date']} {header['time']}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=timezone.utc)
            if entry_dt < cutoff:
                continue
            agent = header["agent"].strip()[:64]
            handoff_id = f"{header['date']} {header['time']}"
            for item in _extract_deferred_items(body):
                scanned += 1
                title = _short_title(item)
                category = _infer_category(item)
                abstract = _ensure_bdd_shape(
                    _truncate_words(item, 1200),
                    category=category,
                    title=title,
                )
                autoissues = [int(n) for n in _AUTOISSUE_REF_RE.findall(item)]
                linked = autoissues[0] if autoissues else None
                if opts["dry_run"]:
                    self.stdout.write(
                        f"[DRY: {category}] #{linked or '-'} {title[:60]}"
                    )
                    continue
                # Dedup via the C++ index first.
                hits = dedup_service.find_similar(abstract, threshold=0.85)
                if hits:
                    skipped_dupe += 1
                    continue
                try:
                    with transaction.atomic():
                        entry = PaperTrailEntry.objects.create(
                            category=category,
                            title=title,
                            abstract=abstract,
                            deferred_by=agent,
                            deferred_in_handoff=handoff_id,
                            severity=PaperTrailEntry.SEVERITY_MEDIUM,
                            linked_autoissue_id=linked,
                            deferral_reason_key="multi_session",
                            # Required-on-new (2026-05-16). Legacy entries
                            # are migrated with placeholder text so the
                            # bulk-import re-run remains idempotent; the
                            # next agent who touches the row can refine.
                            risk_on_inaction=(
                                "Migrated from legacy AGENT-HANDOFF.md prose; "
                                "the original entry did not specify a risk "
                                "field — refine when picking this up."
                            ),
                            acceptance_criteria=(
                                "Migrated from legacy AGENT-HANDOFF.md prose; "
                                "the original entry did not specify acceptance "
                                "criteria — derive from the abstract's Then "
                                "section when picking this up."
                            ),
                        )
                except IntegrityError:
                    # Active (category, fingerprint) row already exists —
                    # collision under the unique constraint, count as dupe.
                    skipped_dupe += 1
                    continue
                entry.deferred_at = djtz.make_aware(
                    entry_dt.replace(tzinfo=None), timezone.utc
                )
                entry.priority_score = compute_priority_score(entry)
                entry.save(update_fields=["deferred_at", "priority_score"])
                dedup_service.add_entry(entry.pk, abstract)
                created += 1

        if opts["dry_run"]:
            self.stdout.write(f"[DRY-RUN: scanned {scanned} candidates]")
        else:
            self.stdout.write(
                f"[PAPER TRAIL MIGRATED: created={created} dedupe-skipped={skipped_dupe} scanned={scanned}]"
            )
