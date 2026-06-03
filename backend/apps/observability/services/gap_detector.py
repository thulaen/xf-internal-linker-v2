from __future__ import annotations

from dataclasses import dataclass

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.observability.api import reserved_metric_names


@dataclass(frozen=True)
class ObservabilityGapFinding:
    category: str
    title: str
    description: str
    external_id: str
    affected_files: list[str]
    severity: str = AutoIssue.SEVERITY_MEDIUM
    priority_score: float = 0.4


def build_gap_findings(
    metric_names: list[str] | None = None,
) -> list[ObservabilityGapFinding]:
    names = metric_names or reserved_metric_names()[:75]
    first_metric = names[0] if names else "reserved-metrics"
    findings = [_reserved_metric_gap(metric_name) for metric_name in names]
    findings.extend([
        _gap(
            "cardinality_overflow",
            "Metric cardinality budget has not been proven",
            "VictoriaMetrics could fill up if labels create too many series.",
            f"cardinality-overflow:{first_metric}",
            ["backend/apps/observability/models.py"],
        ),
        _gap(
            "dashboard_missing",
            "Grafana dashboard provisioning has not been proven",
            "A planned dashboard may be absent or unreachable.",
            "dashboard-missing:grafana",
            ["grafana/dashboards"],
        ),
        _gap(
            "datasource_down",
            "Grafana datasource health has not been proven",
            "A dashboard datasource may fail even when Grafana itself is open.",
            "datasource-down:victoriametrics",
            ["grafana/provisioning/datasources/datasources.yaml"],
        ),
        _gap(
            "vmalert_rule_broken",
            "vmalert rule health has not been proven",
            "A rule syntax error would stop alerts from reaching AutoIssues.",
            "vmalert-rule-broken:rules",
            ["config/vmalert/rules.yml"],
        ),
        _gap(
            "scrape_target_down",
            "vmagent scrape target health has not been proven",
            "A scrape target can be down while the rest of the stack looks healthy.",
            "scrape-target-down:vmagent",
            ["config/vmagent/scrape.yml"],
        ),
    ])
    return findings


def detect_observability_gaps(metric_names: list[str] | None = None) -> int:
    count = 0
    for finding in build_gap_findings(metric_names=metric_names):
        if _file_gap(finding):
            count += 1
    return count


def _reserved_metric_gap(metric_name: str) -> ObservabilityGapFinding:
    return _gap(
        "observability_gap",
        f"Reserved metric not yet proven: {metric_name}",
        (
            "The metric is reserved by the observability spec but has not yet "
            "been proven by a live VictoriaMetrics query."
        ),
        f"metric-gap:{metric_name}",
        ["backend/apps/observability/metric_specs.py"],
    )


def _gap(
    category: str,
    title: str,
    description: str,
    external_id: str,
    affected_files: list[str],
) -> ObservabilityGapFinding:
    return ObservabilityGapFinding(
        category=category,
        title=f"[vmalert] {title}",
        description=description,
        external_id=external_id,
        affected_files=affected_files,
    )


def _file_gap(finding: ObservabilityGapFinding) -> bool:
    fp = canonical_fingerprint(finding.title, finding.external_id)
    issue, _ = upsert_dedup(
        canonical=fp,
        source=getattr(AutoIssue, "SOURCE_VMALERT", AutoIssue.SOURCE_AGENT),
        external_id=finding.external_id,
        fingerprint=fp,
        title=finding.title,
        description=finding.description,
        affected_files=finding.affected_files,
        severity=finding.severity,
        priority_score=finding.priority_score,
        occurrence_count=1,
        category_key=finding.category,
    )
    issue.lessons_learned = _lesson_for(finding)
    issue.save(update_fields=["lessons_learned"])
    return issue is not None


def _lesson_for(finding: ObservabilityGapFinding) -> str:
    return (
        f"Trap: {finding.description} "
        f"Fix shape: prove or repair {finding.category} and rerun the detector."
    )
