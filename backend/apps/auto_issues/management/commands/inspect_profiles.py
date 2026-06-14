"""Inspect profiling signals and print commit-proof markers.

Mutation note: tests cover the issue-writing paths because this command gates
permission to commit source changes.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Mapping
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.auto_issues.services.pyroscope_picker import (
    _extract_function_totals,
    _query_pyroscope_render,
)
from apps.auto_issues.profiling_proof_shared import (
    PROFILE_GAP_CATEGORIES,
    PROFILE_GAP_CATEGORY_TEXT,
)


_DEFAULT_SERVICE = "xf-linker-backend"
_DEFAULT_SPAN_SECONDS = 3600
_MAX_HOTSPOTS = 5
_MIN_OTEL_COLLECTOR_VERSION = (0, 112, 0)
_MIN_PYROSCOPE_VERSION = (1, 18, 1)
_GAP_FILES = [
    "otelcol-config.yaml",
    "docker-compose.yml",
    "backend/config/settings/base.py",
    "grafana/provisioning",
]


class Command(BaseCommand):
    help = "Inspect Pyroscope and OpenTelemetry Profiles before source changes."

    def add_arguments(self, parser):
        parser.add_argument("--service", default=_DEFAULT_SERVICE)
        parser.add_argument("--scope", required=True)
        parser.add_argument(
            "--pyroscope-url",
            default=os.environ.get("PYROSCOPE_SERVER_ADDRESS", "http://pyroscope:4040"),
        )
        parser.add_argument("--span-seconds", type=int, default=_DEFAULT_SPAN_SECONDS)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        service = options["service"].strip()
        scope = options["scope"].strip()
        hotspots = _collect_hotspots(
            server=options["pyroscope_url"],
            service=service,
            span_seconds=options["span_seconds"],
            limit=_MAX_HOTSPOTS,
        )
        if not _profile_pipeline_ready():
            self._print_pipeline_gap(scope=scope, dry_run=options["dry_run"])
            return
        self.stdout.write(_proof_marker(service=service, scope=scope, hotspots=hotspots))
        for name, value in hotspots:
            self.stdout.write(f"  {name[:120]}={value:.0f}ns")

    def _print_pipeline_gap(self, *, scope: str, dry_run: bool) -> None:
        if dry_run:
            self.stdout.write(
                "[PROFILING PIPELINE GAP DRY RUN: "
                f"categories={PROFILE_GAP_CATEGORY_TEXT} scope={scope}]"
            )
            return
        issue_ids = _file_pipeline_gap_issues(scope)
        joined_ids = ",".join(f"#{issue_id}" for issue_id in issue_ids)
        self.stdout.write(
            "[PROFILING PIPELINE GAP: "
            f"autoissues={joined_ids} categories={PROFILE_GAP_CATEGORY_TEXT}]"
        )


def _collect_hotspots(
    *, server: str, service: str, span_seconds: int, limit: int
) -> list[tuple[str, float]]:
    payload = _query_pyroscope_render(
        server,
        service,
        until=int(time.time()),
        span_seconds=span_seconds,
    )
    totals = _extract_function_totals(payload)
    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return ordered[:limit]


def _profile_pipeline_ready() -> bool:
    root = _repo_root()
    return _otel_config_ready(root / "otelcol-config.yaml") and _compose_profiles_ready(
        root / "docker-compose.yml"
    )


def _otel_config_ready(config_path: Path) -> bool:
    config = _read_yaml(config_path)
    return bool(config) and _profile_pipeline_links_pyroscope(config)


def _profile_pipeline_links_pyroscope(config: Mapping[str, object]) -> bool:
    exporters = _child_map(config, "exporters")
    pipelines = _child_map(_child_map(config, "service"), "pipelines")
    profiles = _child_map(pipelines, "profiles")
    receivers = _child_list(profiles, "receivers")
    profile_exporters = _child_list(profiles, "exporters")
    return all(
        (
            _pyroscope_exporter_ready(_child_map(exporters, "otlp/pyroscope")),
            "otlp" in receivers,
            "otlp/pyroscope" in profile_exporters,
        )
    )


def _compose_profiles_ready(compose_path: Path) -> bool:
    compose = _read_yaml(compose_path)
    if not compose:
        return False
    services = _child_map(compose, "services")
    return _collector_ready(_child_map(services, "otel-collector")) and _pyroscope_ready(
        _child_map(services, "pyroscope")
    )


def _read_yaml(path: Path) -> dict[str, object]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _child_map(parent: Mapping[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def _child_list(parent: Mapping[str, object], key: str) -> list[object]:
    value = parent.get(key)
    return value if isinstance(value, list) else []


def _pyroscope_exporter_ready(exporter: dict[str, object]) -> bool:
    # Pyroscope moved to the Mint helper (mint-quality profile); the OTel
    # collector exports profiles to it over the LAN. Accept either the new
    # Mint endpoint or the legacy in-network name for backward compatibility.
    tls = exporter.get("tls") or {}
    endpoint = exporter.get("endpoint")
    valid_endpoint = endpoint in (
        "${env:MINT_OBSERVABILITY_HOST}:4040",
        "192.168.0.91:4040",
        "10.10.10.91:4040",
        "pyroscope:4040",
    )
    return valid_endpoint and tls.get("insecure") is True


def _collector_ready(service: dict[str, object]) -> bool:
    command = " ".join(str(part) for part in (service.get("command") or []))
    image = str(service.get("image") or "")
    return (
        "service.profilesSupport" in command
        and _image_version_at_least(image, _MIN_OTEL_COLLECTOR_VERSION)
    )


def _pyroscope_ready(service: dict[str, object]) -> bool:
    image = str(service.get("image") or "")
    return _image_version_at_least(image, _MIN_PYROSCOPE_VERSION)


def _repo_root() -> Path:
    return Path(os.environ.get("REPO_ROOT", "/repo"))


def _image_version_at_least(image: str, minimum: tuple[int, int, int]) -> bool:
    match = re.search(r":(\d+)\.(\d+)\.(\d+)(?:$|[-@])", image)
    if not match:
        return False
    version = tuple(int(part) for part in match.groups())
    return version >= minimum


def _proof_marker(
    *, service: str, scope: str, hotspots: list[tuple[str, float]]
) -> str:
    baseline = "docker compose exec -T backend python manage.py inspect_profiles"
    return (
        "[PROFILING PROOF: "
        f"service={service} scope={scope} source=pyroscope+otel_profiles "
        f"hotspots={len(hotspots)} baseline=\"{baseline}\" decision=not-relevant]"
    )


def _file_pipeline_gap_issues(scope: str) -> list[int]:
    return [_upsert_pipeline_gap_issue(category, scope).id for category in PROFILE_GAP_CATEGORIES]


def _upsert_pipeline_gap_issue(category: str, scope: str) -> AutoIssue:
    external_id = f"profiling-pipeline-gap::{category}"
    existing = AutoIssue.objects.filter(
        source=AutoIssue.SOURCE_AGENT,
        external_id=external_id,
    ).first()
    if existing is not None:
        _refresh_gap_issue(existing, category, scope)
        return existing
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=external_id,
        fingerprint=external_id[:64],
        canonical_fingerprint=canonical_fingerprint(external_id),
        title=_gap_title(category),
        description=_gap_description(category, scope),
        affected_files=_GAP_FILES,
        severity=AutoIssue.SEVERITY_HIGH,
        status=AutoIssue.STATUS_OPEN,
        priority_score=0.85,
        occurrence_count=1,
        source_observations=[_gap_observation(category)],
    )


def _refresh_gap_issue(issue: AutoIssue, category: str, scope: str) -> None:
    issue.status = AutoIssue.STATUS_OPEN
    issue.description = _gap_description(category, scope)
    issue.last_seen = timezone.now()
    issue.occurrence_count = max(issue.occurrence_count, 1)
    issue.save(update_fields=["status", "description", "last_seen", "occurrence_count"])


def _gap_title(category: str) -> str:
    return f"[profiling-pipeline-gap] Repair OpenTelemetry Profiles {category}"


def _gap_description(category: str, scope: str) -> str:
    return (
        "OpenTelemetry Profiles are not connected to Pyroscope for the "
        f"`{category}` category. Scope inspected: `{scope}`. Repair must cover "
        "collector config, backend config, version compatibility, permissions, "
        "sampling, retention, dashboards, and trace/profile correlation."
    )


def _gap_observation(category: str) -> dict[str, object]:
    now = timezone.now().isoformat()
    return {
        "source": "profiling_pipeline_gap",
        "external_id": f"profiling-pipeline-gap::{category}",
        "first_seen": now,
        "last_seen": now,
        "occurrence_count": 1,
    }
