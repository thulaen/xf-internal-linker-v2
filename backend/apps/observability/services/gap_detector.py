from __future__ import annotations

from dataclasses import dataclass

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.observability.api import reserved_metric_names, registered_metric_names


@dataclass(frozen=True)
class ObservabilityGapFinding:
    category: str
    title: str
    description: str
    external_id: str
    affected_files: list[str]
    severity: str = AutoIssue.SEVERITY_MEDIUM
    priority_score: float = 0.4


_CARDINALITY_BUDGET = 1_000_000


def build_gap_findings(
    metric_names: list[str] | None = None,
    infra_probe=None,
) -> list[ObservabilityGapFinding]:
    names = metric_names or reserved_metric_names()[:75]
    first_metric = names[0] if names else "reserved-metrics"
    # A reserved metric is "proven" once it is registered in the live registry
    # and therefore present in the /metrics exposition that vmagent scrapes.
    # Only a genuinely-unregistered name is a real gap — this replaces the old
    # behaviour of flagging every reserved name unconditionally.
    proven = registered_metric_names()
    unproven = [metric_name for metric_name in names if metric_name not in proven]
    findings = [_reserved_metric_gap(metric_name) for metric_name in unproven]
    # Infra gaps are only filed for categories that fail a live probe of the
    # VictoriaMetrics stack. With no probe (unit tests) we stay conservative and
    # emit them all — no network I/O. The production task passes the live probe,
    # so a healthy stack proves them all and files nothing.
    infra = _all_infra_gaps(first_metric)
    broken = set(infra) if infra_probe is None else _infra_gaps_unproven(infra_probe)
    findings.extend(infra[category] for category in infra if category in broken)
    return findings


def _all_infra_gaps(first_metric: str) -> dict[str, ObservabilityGapFinding]:
    return {
        "cardinality_overflow": _gap(
            "cardinality_overflow",
            "Metric cardinality budget has not been proven",
            "VictoriaMetrics could fill up if labels create too many series.",
            f"cardinality-overflow:{first_metric}",
            ["backend/apps/observability/models.py"],
        ),
        "dashboard_missing": _gap(
            "dashboard_missing",
            "Grafana dashboard provisioning has not been proven",
            "A planned dashboard may be absent or unreachable.",
            "dashboard-missing:grafana",
            ["grafana/dashboards"],
        ),
        "datasource_down": _gap(
            "datasource_down",
            "Grafana datasource health has not been proven",
            "A dashboard datasource may fail even when Grafana itself is open.",
            "datasource-down:victoriametrics",
            ["grafana/provisioning/datasources/datasources.yaml"],
        ),
        "vmalert_rule_broken": _gap(
            "vmalert_rule_broken",
            "vmalert rule health has not been proven",
            "A rule syntax error would stop alerts from reaching AutoIssues.",
            "vmalert-rule-broken:rules",
            ["config/vmalert/rules.yml"],
        ),
        "scrape_target_down": _gap(
            "scrape_target_down",
            "vmagent scrape target health has not been proven",
            "A scrape target can be down while the rest of the stack looks healthy.",
            "scrape-target-down:vmagent",
            ["config/vmagent/scrape.yml"],
        ),
    }


def _default_probe(url: str) -> dict:
    import json
    import urllib.request

    with urllib.request.urlopen(url, timeout=3) as resp:  # nosec B310 - fixed internal URLs
        return json.load(resp)


def _infra_gaps_unproven(probe=None) -> set[str]:
    """Infra-gap categories genuinely broken against the live VictoriaMetrics stack.

    Best-effort: each check probes a service on the docker network. A probe that
    raises (the stack is unreachable, e.g. in a unit-test environment) leaves
    that category UNPROVEN so the finding is still emitted — preserving the
    pre-stack behaviour. When the stack is healthy every category proves and no
    infra gap is filed.
    """
    import urllib.parse

    probe = probe or _default_probe
    broken: set[str] = set()

    def _check(category: str, ok_fn) -> None:
        try:
            if not ok_fn():
                broken.add(category)
        except Exception:  # noqa: BLE001 - unreachable stack => unproven, not crash.
            broken.add(category)

    def _targets_ok() -> bool:
        targets = probe("http://vmagent:8429/api/v1/targets")["data"]["activeTargets"]
        # pyroscope runs on the Mint helper; its local-name scrape is expected down.
        return all(
            t.get("health") == "up"
            for t in targets
            if (t.get("labels", {}).get("job") or "") != "pyroscope"
        )

    def _rules_ok() -> bool:
        groups = probe("http://vmalert:8880/api/v1/rules")["data"]["groups"]
        rules = [rule for group in groups for rule in group.get("rules", [])]
        return bool(rules) and all(rule.get("health") == "ok" for rule in rules)

    def _cardinality_ok() -> bool:
        expr = urllib.parse.quote('count({__name__=~".+"})')
        result = probe(f"http://vmsingle:8428/api/v1/query?query={expr}")["data"]["result"]
        return bool(result) and float(result[0]["value"][1]) < _CARDINALITY_BUDGET

    def _datasource_ok() -> bool:
        expr = urllib.parse.quote("vm_app_version")
        return probe(f"http://vmsingle:8428/api/v1/query?query={expr}")["status"] == "success"

    def _grafana_ok() -> bool:
        return probe("http://grafana:3000/api/health")["database"] == "ok"

    _check("scrape_target_down", _targets_ok)
    _check("vmalert_rule_broken", _rules_ok)
    _check("cardinality_overflow", _cardinality_ok)
    _check("datasource_down", _datasource_ok)
    _check("dashboard_missing", _grafana_ok)
    return broken


def detect_observability_gaps(metric_names: list[str] | None = None) -> int:
    # Production path: probe the live VictoriaMetrics stack so a healthy stack
    # files no infra gaps. (build_gap_findings with no probe — used by unit
    # tests — stays hermetic and emits them all.)
    count = 0
    for finding in build_gap_findings(metric_names=metric_names, infra_probe=_default_probe):
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
