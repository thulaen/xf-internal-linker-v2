"""Retire OPEN AutoIssue + paper-trail work tied to a REMOVED backend language.

Plain-English summary
---------------------
The backend is now "Python plus Rust only" (decision record
docs/adr/0007-python-rust-two-language.md). C, C++, Go, Haskell, and Lua are
removed. A lot of old tracked work — open AutoIssues and open paper-trail
entries — still describes Go services, Haskell, Lua, and the mutation tools that
only existed for those removed languages. That work can never be done now, so it
should be closed out cleanly instead of sitting in the open queues forever.

This command finds that removed-language work and closes it:

- AutoIssues: the model has no "wontfix"/"stale" status (only open / picked /
  fixing / resolved / deferred). So the command sets such issues to ``resolved``
  with a two-part ``Trap: ... Fix shape: ...`` ``lessons_learned`` note citing
  ADR 0007. ``resolved`` is the model's terminal closed state.
- Paper-trail entries: the model HAS a ``stale`` status (which requires a
  ``suppression_reason``). The command sets such entries to ``stale`` with a
  ``suppression_reason`` citing ADR 0007.

SAFETY — what this command will NEVER touch:
- ``rust_defect`` source AutoIssues (Rust is authoritative and stays).
- Pure-Python issues (Python stays).
- C / C++ work of any kind. C and C++ are mid-migration: Rust kernels are still
  being ported and the C++ lifecycle hooks are still active. Retiring C/C++ work
  now would be wrong. The matcher explicitly EXCLUDES anything that mentions
  C or C++ (cpp, c++, .cpp, pybind, papertrail_dedup, etc.).
- Live sidecar Python clients (e.g. ``_sidecars/snapshotd_client.py``). The
  ``sidecars`` Go service is still running and its Python clients are in use, so
  test-case rows for those Python files are NOT removed-language work.

Default mode is ``--dry-run`` (TRUE). Pass ``--apply`` to actually write.

Citations:
- docs/adr/0007-python-rust-two-language.md (decision of record)
- docs/PYTHON-RUST-MIGRATION-PLAN.md
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.auto_issues.models import AutoIssue

# --- Matcher configuration -------------------------------------------------
#
# A row counts as removed-language work only when (a) it matches one of the
# removed-language signals below AND (b) it does NOT match any guard term.
# Both checks are case-insensitive substring tests on the combined
# title + description + affected_files text.

ADR_REF = "docs/adr/0007-python-rust-two-language.md"

# Removed languages / tooling that are genuinely gone per ADR 0007.
# C and C++ are deliberately NOT here — they are mid-port and still gated.
#
# Signals are deliberately SPECIFIC. Broad signals were tried and rejected:
#   - bare "lua" matched "evaLUAte" inside Prometheus-rule descriptions.
#   - bare ".go " / ".go:" matched Go stack frames (engine.go, manager.go)
#     inside Loki / VictoriaMetrics / Prometheus log lines — those are
#     THIRD-PARTY observability binaries we KEEP, not our removed Go services.
# So every signal below names a removed language or its tooling explicitly,
# never a bare extension or a substring that collides with English words.
REMOVED_SIGNALS: dict[str, tuple[str, ...]] = {
    "haskell": ("haskell", "mucheck", "hlint", "cabal build", "stack build", ".hs:"),
    "lua": ("luajit", "luacheck", "lua mutation", "lua sandbox", "lua test", "lua script", ".lua"),
    "go": (
        "golang",
        "go-mutesting",
        "go vet",
        "golangci",
        "go service",
        "go-service",
        "go services tier",
        "go sidecar",
        "go mutation",
        "go test -",
    ),
}

# Extra guard: third-party observability binaries are written in Go and spew
# Go stack frames into Loki. They are infrastructure we KEEP. If a row reads
# like an observability log line, never treat it as removed-Go work.
OBSERVABILITY_NOISE: tuple[str, ...] = (
    "loki:",
    "victoriametrics",
    "promscrape",
    "prometheusexporter",
    "frontend_scheduler",
    "caller=manager",
    "caller=engine",
    "caller=ratestore",
    "caller=frontend",
)

# Guard terms — if ANY of these appear, the row is NOT retired. These protect
# C/C++ (mid-port), Rust (stays), Python (stays), and the live sidecar Python
# clients (still in use while the Go sidecars binary runs).
GUARD_TERMS: tuple[str, ...] = (
    # C / C++ — never retire while kernels are mid-port and C++ hooks active.
    "c++",
    "cpp",
    ".cpp",
    ".cc ",
    ".hpp",
    "pybind",
    "papertrail_dedup",
    "clang",
    "gwp",
    "perfetto",
    # Rust stays / is authoritative.
    "rust",
    "cargo",
    "clippy",
    "maturin",
    "pyo3",
    # Live sidecar Python clients (still used). _sidecars/ paths and the
    # specific running sidecar service names route to Python files in use.
    "_sidecars",
    "sidecars_pb",
    "snapshotd",
    "bullboard",
    "attrouted",
    "schemard",
    "coordd",
    "errord",
    "searchd",
    "streamd",
    "startupd",
)


@dataclass(frozen=True)
class Classification:
    """Result of classifying one row. ``language`` is None when not retirable."""

    language: str | None


def _row_text(title: str, description: str, affected_files) -> str:
    files = " ".join(str(p) for p in (affected_files or []))
    return f" {title} {description} {files} ".lower()


def classify_removed_language(
    title: str,
    description: str,
    source: str,
    affected_files=None,
) -> Classification:
    """Decide whether one row is removed-language work that may be retired.

    Returns a Classification whose ``language`` is the removed language tag
    (``haskell`` / ``lua`` / ``go``) when retirable, else ``None``.

    A row is retirable only when it matches a removed-language signal AND does
    not match any guard term AND is not from the ``rust_defect`` source.
    """
    if source == AutoIssue.SOURCE_RUST_DEFECT:
        return Classification(None)

    text = _row_text(title, description, affected_files)

    for noise in OBSERVABILITY_NOISE:
        if noise in text:
            return Classification(None)

    for guard in GUARD_TERMS:
        if guard in text:
            return Classification(None)

    for language, signals in REMOVED_SIGNALS.items():
        for signal in signals:
            if signal in text:
                return Classification(language)

    return Classification(None)


def _retire_lessons(language: str) -> str:
    return (
        f"Trap: this AutoIssue tracked {language} work, but {language} is a "
        f"removed backend language per {ADR_REF} (backend is Python + Rust only). "
        f"The work can never be completed and was cluttering the open queue. "
        f"Fix shape: closed it as resolved (the AutoIssue model has no "
        f"wontfix/stale status) with a note citing ADR 0007 so future agents "
        f"know it was retired, not fixed."
    )


def _suppression_reason(language: str) -> str:
    return (
        f"Removed-language work: {language} is removed per {ADR_REF} "
        f"(backend is Python + Rust only). Marked stale because the work can "
        f"never be done."
    )


class Command(BaseCommand):
    help = (
        "Retire OPEN AutoIssue + paper-trail entries tied to a removed backend "
        "language (Go / Haskell / Lua and their mutation tooling). Keeps Rust, "
        "Python, C/C++ (mid-port), and live sidecar Python clients untouched. "
        "Dry-run by default; pass --apply to write."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write the status changes. Default is a dry-run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Show what would change without writing (the default).",
        )
        parser.add_argument("--agent", default="claude")

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))

        autoissue_hits = self._collect_autoissues()
        papertrail_hits = self._collect_papertrail()

        if apply_changes:
            self._apply_autoissues(autoissue_hits, options["agent"])
            self._apply_papertrail(papertrail_hits)
            verb = "RETIRED"
        else:
            verb = "DRY-RUN"

        self.stdout.write(
            f"[REMOVED-LANGUAGE {verb}: autoissues={len(autoissue_hits)} "
            f"paper_trail={len(papertrail_hits)} adr={ADR_REF}]"
        )
        for issue, language in autoissue_hits[:50]:
            self.stdout.write(f"  AutoIssue #{issue.id} [{language}] {str(issue.title)[:80]}")
        for entry, language in papertrail_hits[:50]:
            self.stdout.write(f"  PaperTrail #{entry.id} [{language}] {str(entry.title)[:80]}")

    # --- collection -------------------------------------------------------

    def _collect_autoissues(self) -> list[tuple[AutoIssue, str]]:
        open_states = (
            AutoIssue.STATUS_OPEN,
            AutoIssue.STATUS_PICKED,
            AutoIssue.STATUS_FIXING,
        )
        hits: list[tuple[AutoIssue, str]] = []
        qs = AutoIssue.objects.filter(status__in=open_states).only(
            "id", "title", "description", "source", "affected_files", "status"
        )
        for issue in qs.iterator():
            result = classify_removed_language(
                str(issue.title or ""),
                str(issue.description or ""),
                issue.source,
                issue.affected_files,
            )
            if result.language is not None:
                hits.append((issue, result.language))
        return hits

    def _collect_papertrail(self) -> list:
        try:
            from apps.paper_trail.models import PaperTrailEntry
        except Exception:  # noqa: BLE001 — app may be absent in minimal test setups
            return []

        active = PaperTrailEntry._ACTIVE_STATUSES
        hits = []
        qs = PaperTrailEntry.objects.filter(status__in=active).only(
            "id", "title", "abstract", "affected_files", "status"
        )
        for entry in qs.iterator():
            result = classify_removed_language(
                str(entry.title or ""),
                str(getattr(entry, "abstract", "") or ""),
                "paper_trail",
                entry.affected_files,
            )
            if result.language is not None:
                hits.append((entry, result.language))
        return hits

    # --- apply ------------------------------------------------------------

    def _apply_autoissues(self, hits, agent: str) -> None:
        now = timezone.now()
        for issue, language in hits:
            issue.status = AutoIssue.STATUS_RESOLVED
            issue.resolved_at = now
            issue.resolved_by = agent[:64]
            issue.lessons_learned = _retire_lessons(language)
            issue.save(
                update_fields=[
                    "status",
                    "resolved_at",
                    "resolved_by",
                    "lessons_learned",
                ]
            )

    def _apply_papertrail(self, hits) -> None:
        from apps.paper_trail.models import PaperTrailEntry

        for entry, language in hits:
            entry.status = PaperTrailEntry.STATUS_STALE
            entry.suppression_reason = _suppression_reason(language)
            entry.save(update_fields=["status", "suppression_reason"])
