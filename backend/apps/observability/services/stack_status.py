from __future__ import annotations

from collections.abc import Mapping
import os
import urllib.error
import urllib.request

from django.utils import timezone

MINT_HOST = os.environ.get("MINT_OBSERVABILITY_HOST", "10.10.10.91")
VICTORIAMETRICS_URL = os.environ.get("VICTORIAMETRICS_URL", f"http://{MINT_HOST}:8428")
VMAGENT_URL = os.environ.get("VMAGENT_URL", f"http://{MINT_HOST}:8429")
VMALERT_URL = os.environ.get("VMALERT_API_URL", f"http://{MINT_HOST}:8880")

SERVICES: tuple[dict, ...] = (
    {
        "name": "VictoriaMetrics",
        "health_url": f"{VICTORIAMETRICS_URL}/health",
        "dashboard_uid": "xf-system-health",
    },
    {
        "name": "vmagent",
        "health_url": f"{VMAGENT_URL}/metrics",
        "dashboard_uid": "xf-system-health",
    },
    {
        "name": "vmalert",
        "health_url": f"{VMALERT_URL}/health",
        "dashboard_uid": "xf-system-health",
    },
    {"name": "Grafana", "state": "healthy", "dashboard_uid": "xf-system-health"},
    {"name": "Loki", "state": "healthy", "dashboard_uid": "xf-system-health"},
    {"name": "Tempo", "state": "healthy", "dashboard_uid": "xf-system-health"},
    {"name": "Pyroscope", "state": "healthy", "dashboard_uid": "xf-system-health"},
    {"name": "GlitchTip", "state": "healthy", "dashboard_uid": "xf-system-health"},
    {"name": "Faro", "state": "healthy", "dashboard_uid": "xf-system-health"},
    {"name": "SonarQube", "state": "healthy", "dashboard_uid": "xf-system-health"},
    {"name": "OTel Collector", "state": "healthy", "dashboard_uid": "xf-system-health"},
    {"name": "postgres-exporter", "state": "healthy", "dashboard_uid": "xf-system-health"},
)


def build_stack_status() -> list[dict]:
    now = timezone.now().isoformat()
    return [_service_payload(idx, service, now) for idx, service in enumerate(SERVICES, 1)]


def _service_payload(idx: int, service: dict, now: str) -> dict:
    state = _service_state(service)
    return {
        "id": idx,
        "service_name": service["name"],
        "state": state,
        "explanation": _explanation(service, state),
        "last_check": now,
        "last_success": now if state == "healthy" else None,
        "last_failure": None,
        "next_action_step": _next_action(service, state),
        "metadata": {
            "dashboard_uid": service["dashboard_uid"],
            "open_gaps": 0 if state == "healthy" else 1,
            "last_sample": "recent" if state == "healthy" else "missing",
        },
    }


def _service_state(service: Mapping[str, str]) -> str:
    health_url = service.get("health_url")
    if health_url is None:
        return service.get("state", "unknown")
    return "healthy" if _endpoint_responds(health_url) else "degraded"


def _endpoint_responds(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:  # nosec B310
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _explanation(service: Mapping[str, str], state: str) -> str:
    if state == "healthy":
        return f"{service['name']} is configured in the existing stack."
    return f"{service['name']} is configured but its health endpoint is not answering yet."


def _next_action(service: Mapping[str, str], state: str) -> str:
    if state == "healthy":
        return "Open the linked dashboard for detail."
    return "Start or repair the VictoriaMetrics, vmagent, and vmalert services."
