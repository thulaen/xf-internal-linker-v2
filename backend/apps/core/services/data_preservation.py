"""Protected data manifest and migration-safety scanner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ProtectedDataRule:
    """One table's storage policy for migration safety checks."""

    table: str
    policy: str
    reason: str


PROTECTED_DATA_RULES: tuple[ProtectedDataRule, ...] = (
    ProtectedDataRule("auth_user", "current_state", "operator accounts"),
    ProtectedDataRule("authtoken_token", "current_state", "login tokens"),
    ProtectedDataRule("core_appsetting", "current_state", "settings and secrets"),
    ProtectedDataRule("content_contentitem", "current_state", "live content rows"),
    ProtectedDataRule("content_post", "current_state", "live post bodies"),
    ProtectedDataRule("content_sentence", "current_state", "current sentence rows"),
    ProtectedDataRule(
        "content_passageembedding", "current_state", "current passage vectors"
    ),
    ProtectedDataRule(
        "analytics_searchmetric", "current_state", "GSC/GA4/Matomo metrics"
    ),
    ProtectedDataRule(
        "analytics_gscdailyperformance", "current_state", "GSC daily data"
    ),
    ProtectedDataRule(
        "crawler_crawledpagemeta", "current_state", "crawl page metadata"
    ),
    ProtectedDataRule("graph_existinglink", "current_state", "current graph links"),
    ProtectedDataRule(
        "knowledge_graph_pixiewalkvisit", "current_state", "Pixie walk state"
    ),
    ProtectedDataRule("suggestions_weightpreset", "current_state", "ranking settings"),
    ProtectedDataRule(
        "suggestions_suggestion", "event_history", "operator review history"
    ),
    ProtectedDataRule(
        "suggestions_suggestionimpression", "event_history", "behavior history"
    ),
    ProtectedDataRule(
        "suggestions_weightadjustmenthistory", "event_history", "auto-tuning history"
    ),
    ProtectedDataRule("sync_syncjob", "event_history", "import/sync summaries"),
    ProtectedDataRule("crawler_crawlervisit", "event_history", "bounded crawl visits"),
    ProtectedDataRule("audit_auditentry", "event_history", "operator audit trail"),
    ProtectedDataRule("audit_errorlog", "event_history", "diagnostic history"),
)

ALLOWED_HISTORICAL_DESTRUCTIVE_MIGRATIONS = frozenset(
    {
        "backend/apps/content/migrations/0010_bge_m3_embedding_dim_1024.py",
        "backend/apps/content/migrations/0006_remove_contentitem_pagerank_score_and_more.py",
        "backend/apps/content/migrations/0038_passage_overlap_rechunk.py",
        "backend/apps/core/migrations/0015_delete_featureflag_delete_featureflagexposure.py",
        "backend/apps/core/migrations/0010_runtimeauditlog_helpernode_accepting_work_and_more.py",
        "backend/apps/crawler/migrations/0004_collapse_crawled_page_meta_duplicates.py",
        "backend/apps/diagnostics/migrations/0004_purge_http_worker_rows.py",
        "backend/apps/diagnostics/migrations/0001_initial.py",
        "backend/apps/analytics/migrations/0005_gscdailyperformance_gscimpactsnapshot.py",
        "backend/apps/pipeline/migrations/0002_embedding_infra.py",
        "backend/apps/suggestions/migrations/0004_remove_suggestion_score_pagerank.py",
        "backend/apps/suggestions/migrations/0034_drop_meta_tournament_tables.py",
    }
)

_DESTRUCTIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("full table delete", re.compile(r"\.objects\.all\(\)\.delete\(")),
    ("model delete", re.compile(r"migrations\.DeleteModel\(")),
    ("field removal", re.compile(r"migrations\.RemoveField\(")),
    (
        "raw drop/truncate",
        re.compile(
            r"(RunSQL|schema_editor\.execute).*?\b(DROP\s+TABLE|TRUNCATE)\b",
            re.IGNORECASE,
        ),
    ),
    ("vector nulling", re.compile(r"\b(embedding|vector)[\w_]*\s*=\s*None\b")),
)

_CREATE_ARTIFACT_PATTERN = re.compile(
    r"migrations\.CreateModel\(\s*name=['\"][\w]*(Embedding|Vector|Snapshot|Fingerprint)",
    re.IGNORECASE | re.DOTALL,
)
_INVARIANT_FIELDS = (
    "content_hash",
    "text_hash",
    "embedding_text_hash",
    "signal_version",
    "model_version",
)


@dataclass(frozen=True)
class MigrationSafetyFinding:
    """One migration-safety issue found in a migration file."""

    path: str
    line: int
    kind: str
    detail: str


def scan_migration_text(path: str, text: str) -> list[MigrationSafetyFinding]:
    """Return unsafe destructive or duplicate-artifact patterns in one file."""
    findings: list[MigrationSafetyFinding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _DESTRUCTIVE_PATTERNS:
            if pattern.search(line):
                findings.append(
                    MigrationSafetyFinding(path, line_no, kind, line.strip())
                )
    if _CREATE_ARTIFACT_PATTERN.search(text) and not any(
        key in text for key in _INVARIANT_FIELDS
    ):
        findings.append(
            MigrationSafetyFinding(
                path,
                1,
                "duplicate artifact risk",
                "artifact model lacks content hash/version fields",
            )
        )
    return findings


def scan_migration_file(path: Path, repo_root: Path) -> list[MigrationSafetyFinding]:
    """Scan one migration file unless it is a documented historical exception."""
    rel_path = path.relative_to(repo_root).as_posix()
    if rel_path in ALLOWED_HISTORICAL_DESTRUCTIVE_MIGRATIONS:
        return []
    return scan_migration_text(rel_path, path.read_text(encoding="utf-8"))


def scan_repo_migrations(repo_root: Path) -> list[MigrationSafetyFinding]:
    """Scan all app migrations for unsafe data-loss patterns."""
    migrations_root = repo_root / "backend" / "apps"
    findings: list[MigrationSafetyFinding] = []
    for path in migrations_root.glob("*/migrations/*.py"):
        if path.name == "__init__.py":
            continue
        findings.extend(scan_migration_file(path, repo_root))
    return findings
