"""Pure postgres-exporter metric parsing + threshold rules (no DB, no network).

`parse_prometheus_text` turns Prometheus text-exposition format into Sample
rows. `evaluate_rules` applies cited PostgreSQL health thresholds and returns
Findings. The orchestration that fetches metrics and files AutoIssues lives in
pgexporter_picker.py. Thresholds are documented + cited in
docs/specs/fr-pgexporter-autoissues.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from collections.abc import Iterable

from apps.auto_issues.models import AutoIssue

# Per-database rules skip PostgreSQL's built-in maintenance databases — health
# there is not actionable application signal.
_SYSTEM_DBS = frozenset({"template0", "template1", "postgres"})

# Cache-hit ratio is only meaningful once the database has served enough block
# reads to judge; below this many total blocks the rule stays silent.
_MIN_CACHE_BLOCKS = 100
_CACHE_HIT_FLOOR = 0.99
_CONNECTION_SATURATION = 0.8

_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?P<labels>\{[^}]*\})?\s+(?P<value>.+?)\s*$"
)
_LABEL_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


@dataclass(frozen=True)
class Sample:
    name: str
    labels: dict
    value: float


@dataclass(frozen=True)
class Finding:
    key: str
    title: str
    description: str
    severity: str
    fingerprint: str
    affected: list = field(default_factory=list)


def parse_prometheus_text(text: str) -> list[Sample]:
    """Parse Prometheus text exposition format into Samples, skipping junk."""
    samples: list[Sample] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _SAMPLE_RE.match(stripped)
        if match is None:
            continue
        value = _parse_value(match.group("value"))
        if value is None:
            continue
        labels = dict(_LABEL_RE.findall(match.group("labels") or ""))
        samples.append(Sample(name=match.group("name"), labels=labels, value=value))
    return samples


def _parse_value(raw: str) -> float | None:
    token = raw.strip()
    try:
        return float(token)
    except (TypeError, ValueError):
        return None


def evaluate_rules(samples: Iterable[Sample]) -> list[Finding]:
    """Apply every health rule and return the union of findings."""
    samples = list(samples)
    findings: list[Finding] = []
    findings.extend(_rule_pg_down(samples))
    findings.extend(_rule_deadlocks(samples))
    findings.extend(_rule_cache_hit(samples))
    findings.extend(_rule_connection_saturation(samples))
    return findings


def _by_name(samples: list[Sample], name: str) -> list[Sample]:
    return [s for s in samples if s.name == name]


def _real_db(sample: Sample) -> bool:
    return sample.labels.get("datname", "") not in _SYSTEM_DBS


def _rule_pg_down(samples: list[Sample]) -> list[Finding]:
    for sample in _by_name(samples, "pg_up"):
        if sample.value == 0.0:
            return [Finding(
                key="pg_up_down",
                title="PostgreSQL is unreachable (pg_up = 0)",
                description=(
                    "postgres-exporter could not connect to PostgreSQL on its "
                    "last scrape. The database or its network path is down."
                ),
                severity=AutoIssue.SEVERITY_CRITICAL,
                fingerprint="pgexporter:pg_up_down",
            )]
    return []


def _rule_deadlocks(samples: list[Sample]) -> list[Finding]:
    findings: list[Finding] = []
    for sample in _by_name(samples, "pg_stat_database_deadlocks"):
        if not _real_db(sample) or sample.value <= 0:
            continue
        db = sample.labels.get("datname", "?")
        findings.append(Finding(
            key="deadlocks",
            title=f"Deadlocks detected on database {db}",
            description=(
                f"pg_stat_database_deadlocks for {db} is {int(sample.value)}. "
                "Concurrent transactions are blocking each other; review lock "
                "ordering and transaction scope."
            ),
            severity=AutoIssue.SEVERITY_HIGH,
            fingerprint=f"pgexporter:deadlocks:{db}",
        ))
    return findings


def _rule_cache_hit(samples: list[Sample]) -> list[Finding]:
    hits = {s.labels.get("datname", "?"): s.value for s in _by_name(samples, "pg_stat_database_blks_hit")}
    reads = {s.labels.get("datname", "?"): s.value for s in _by_name(samples, "pg_stat_database_blks_read")}
    findings: list[Finding] = []
    for db, hit in hits.items():
        if db in _SYSTEM_DBS:
            continue
        read = reads.get(db, 0.0)
        total = hit + read
        if total < _MIN_CACHE_BLOCKS:
            continue
        ratio = hit / total
        if ratio < _CACHE_HIT_FLOOR:
            findings.append(Finding(
                key="cache_hit",
                title=f"Low buffer-cache hit ratio on {db} ({ratio:.1%})",
                description=(
                    f"pg_stat_database cache hit ratio for {db} is {ratio:.3f}, "
                    f"below {_CACHE_HIT_FLOOR}. Queries are hitting disk; review "
                    "indexes, shared_buffers, or query plans."
                ),
                severity=AutoIssue.SEVERITY_MEDIUM,
                fingerprint=f"pgexporter:cache_hit:{db}",
            ))
    return findings


def _rule_connection_saturation(samples: list[Sample]) -> list[Finding]:
    active = sum(s.value for s in _by_name(samples, "pg_stat_activity_count"))
    max_samples = _by_name(samples, "pg_settings_max_connections")
    if not max_samples:
        return []
    limit = max_samples[0].value
    if limit <= 0 or (active / limit) <= _CONNECTION_SATURATION:
        return []
    return [Finding(
        key="connection_saturation",
        title=f"Connection pool near saturation ({int(active)}/{int(limit)})",
        description=(
            f"{int(active)} of {int(limit)} PostgreSQL connections are in use "
            f"(> {_CONNECTION_SATURATION:.0%}). New connections risk being "
            "refused; check pooling and leaked connections."
        ),
        severity=AutoIssue.SEVERITY_HIGH,
        fingerprint="pgexporter:connection_saturation",
    )]
