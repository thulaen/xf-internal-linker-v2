"""Probe every Kubernetes observability service (Phase K.4).

Sticky #1 (paper_trail row 11) names this as a session-start ritual. It now
uses the Kubernetes API to verify each observability pod is Running and Ready.

Each failing signal is filed as a deduped AutoIssue under the existing
``observability`` category so the next session-start ritual picks it
up. The command also emits a single line of the form
``[OBSERVABILITY HEALTH: status=healthy|degraded failing_signals=<list>]``
that the agent pastes into the AGENT-HANDOFF entry.

The command is intentionally a session-start advisory, not a pre-commit
gate. The pre-commit ``check-observability-stack`` hook (Phase L)
already blocks code-changing commits when any tier container is down;
this command's role is to surface degraded signals as actionable
AutoIssues for the next priority-1 read.

Run:
    python scripts/backend_manage.py check_observability_health
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory


# Single source of truth for the observability + quality tier. The
# .githooks/check-observability-stack.py pre-commit hook reads the same
# JSON so the two enforcement points never drift. glitchtip-init is
# intentionally excluded because it is an init job that exits after
# running. See docs/specs/fr-observability-always-on-and-no-deferral.md.
_CONTAINER_REPO_ROOT = Path("/repo")
_CONFIG_RELATIVE_PATH = Path("config") / "observability-services.json"


def _services_config_path() -> Path:
    """Resolve config/observability-services.json.

    The repo is mounted at ``/repo`` inside Docker containers (the
    location of the JSON the pre-commit hook also reads).  Outside the
    container the file lives at ``<repo>/config/observability-services
    .json``; we discover it by walking up from this module until we hit
    a directory that contains ``config/observability-services.json``.
    """
    candidate = _CONTAINER_REPO_ROOT / _CONFIG_RELATIVE_PATH
    if candidate.is_file():
        return candidate
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _CONFIG_RELATIVE_PATH
        if candidate.is_file():
            return candidate
    # Fall through with the last candidate so callers see a clear error path.
    return _CONTAINER_REPO_ROOT / _CONFIG_RELATIVE_PATH


def _load_services() -> tuple[str, ...]:
    try:
        payload = json.loads(_services_config_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ()
    services = payload.get("services") or []
    return tuple(str(name) for name in services if isinstance(name, str))


def _observability_services() -> tuple[str, ...]:
    """Return the observability tier services list.

    Resolved lazily on each call so test fixtures that monkey-patch
    the config file path see fresh data.  The constant ``OBSERVABILITY
    _SERVICES`` below memoises the first lookup for callers that prefer
    the module-level form (existing tests use this name).
    """
    return _load_services()


OBSERVABILITY_SERVICES = _observability_services()

# States the hook accepts. ``starting`` is intentional — SonarQube takes
# 60-120 seconds to initialise its Elasticsearch index, and blocking on
# ``starting`` would add a 1-2-minute lag the user explicitly rejected.
_FALLBACK_HEALTH = ""
_CATEGORY_KEY = "observability"
_K8S_NAMESPACE = "xf-obs"
_K8S_TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
_K8S_CA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")


def _kubernetes_pods_for_service(service: str, timeout: int = 15) -> list[dict]:
    """Return pod records for a service label from the in-cluster API."""
    try:
        token = _K8S_TOKEN_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return []
    if not token:
        return []
    selector = urllib.parse.quote(f"app={service}")
    url = (
        "https://kubernetes.default.svc/api/v1/namespaces/"
        f"{_K8S_NAMESPACE}/pods?labelSelector={selector}"
    )
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    context = ssl.create_default_context(cafile=str(_K8S_CA_PATH)) if _K8S_CA_PATH.exists() else None
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    return [item for item in items or [] if isinstance(item, dict)]


def _service_state(service: str) -> tuple[str, str]:
    """Return ``(state, health)`` for a Kubernetes observability signal."""
    pods = _kubernetes_pods_for_service(service)
    if not pods:
        return "absent", _FALLBACK_HEALTH
    for pod in pods:
        status = pod.get("status") or {}
        phase = str(status.get("phase") or "unknown")
        if phase != "Running":
            return phase, "not-ready"
        statuses = status.get("containerStatuses") or []
        if not statuses:
            return phase, "unknown"
        not_ready = [item for item in statuses if not item.get("ready")]
        if not_ready:
            return phase, "not-ready"
    return "Running", "Ready"


def _is_signal_healthy(state: str, health: str) -> bool:
    return state == "Running" and health == "Ready"


def _file_failure(category: AutoIssueCategory, service: str, state: str, health: str) -> int:
    """File or dedup an AutoIssue for a failing signal; return the row id."""
    title = f"observability signal degraded: {service}"
    body = (
        f"{service} Kubernetes pod state is '{state}' and health is "
        f"'{health or 'unknown'}'. The Observability-Always-On rule "
        "requires this service to remain running for the entire session. "
        f"Repair the Kubernetes deployment for {service} in namespace {_K8S_NAMESPACE}."
    )
    canonical_fingerprint = f"observability:{service}:{state}:{health or 'unknown'}"
    existing = AutoIssue.objects.filter(canonical_fingerprint=canonical_fingerprint).first()
    if existing is not None:
        existing.occurrence_count = (existing.occurrence_count or 0) + 1
        existing.last_seen = timezone.now()
        existing.save(update_fields=["occurrence_count", "last_seen"])
        return existing.id
    auto = AutoIssue.objects.create(
        title=title,
        description=body,
        category=category,
        source=AutoIssue.SOURCE_AGENT,
        external_id=canonical_fingerprint,
        severity=AutoIssue.SEVERITY_HIGH,
        status=AutoIssue.STATUS_OPEN,
        canonical_fingerprint=canonical_fingerprint,
        priority_score=200,
        affected_files=[],
    )
    return auto.id


class Command(BaseCommand):
    """Probe the observability + quality tier and report degraded signals."""

    help = (
        "Probe every container in the observability + quality tier. "
        "Files an AutoIssue per failing signal and emits the "
        "[OBSERVABILITY HEALTH: ...] marker for the AGENT-HANDOFF entry."
    )

    def add_arguments(self, parser):  # pragma: no cover - trivial
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Probe but do not file AutoIssues (preview mode).",
        )

    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]
        category, _ = AutoIssueCategory.objects.get_or_create(
            key=_CATEGORY_KEY,
            defaults={
                "label": "Observability",
                "description": "Metrics, traces, error context, and monitoring hooks.",
                "sort_order": 120,
            },
        )

        failures: list[tuple[str, str, str, int]] = []
        for service in OBSERVABILITY_SERVICES:
            state, health = _service_state(service)
            if _is_signal_healthy(state, health):
                continue
            if dry_run:
                row_id = -1
            else:
                row_id = _file_failure(category, service, state, health)
            failures.append((service, state, health, row_id))

        status = "healthy" if not failures else "degraded"
        if failures:
            failing_signals = ",".join(name for name, *_ in failures)
            id_list = ",".join(f"#{row_id}" for _, _, _, row_id in failures)
            self.stdout.write(
                f"[OBSERVABILITY HEALTH: status={status} "
                f"failing_signals={failing_signals} autoissues={id_list}]"
            )
            for service, state, health, row_id in failures:
                self.stdout.write(
                    f"  {service}: state={state} health={health or 'unknown'} "
                    f"autoissue=#{row_id}"
                )
        else:
            self.stdout.write(
                f"[OBSERVABILITY HEALTH: status={status} failing_signals=none]"
            )
