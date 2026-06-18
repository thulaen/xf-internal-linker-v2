"""DRF views backing the MCP / AI Agents page in the frontend.

KISS — five endpoints in one file. No new ViewSets, no fancy permissions
beyond IsAuthenticated. Everything is read-mostly except `run-monthly` which
just shells the management command via Django's call_command in a thread.

Routes (registered in apps/api/urls.py):
    GET  /api/mcp/health/         — is the MCP wiring alive?
    GET  /api/mcp/agents/         — install + config status of Claude Code / Codex / Antigravity
    POST /api/mcp/run-monthly/    — kick the monthly Top-50 job manually (Run Now button)
    GET  /api/schedules/          — registered schedules + their last runs (sentient schedules)
    POST /api/schedules/<task>/run-now/  — manual fire of any registered schedule
"""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from rest_framework import status as drf_status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# /api/mcp/health/
# ────────────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mcp_health(request):
    """Tell the UI whether MCP wiring is in place.

    KISS v1 checks for the presence of the project-scope `.mcp.json` and the
    `mcp` Python package. If both exist, MCP is "live" — the actual stdio
    server runs on demand inside the backend container when Claude Code
    spawns it, so there's no long-lived process to ping.
    """
    repo_root = _repo_root()
    mcp_json = repo_root / ".mcp.json"
    server_path = repo_root / "backend" / "mcp_server.py"
    has_mcp_pkg = _has_python_pkg("mcp")
    alive = mcp_json.exists() and server_path.exists() and has_mcp_pkg
    return Response(
        {
            "alive": alive,
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mcp_json_present": mcp_json.exists(),
            "server_script_present": server_path.exists(),
            "mcp_python_pkg_installed": has_mcp_pkg,
            "transport": "stdio through Kubernetes backend runner",
            "tools_exposed": [
                "get_top_candidates",
                "get_dashboard_metrics",
                "list_orphans",
            ],
        }
    )


# ────────────────────────────────────────────────────────────────────
# /api/mcp/agents/
# ────────────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mcp_agents(request):
    """Best-effort detection of which AI agents are installed on the host.

    KISS v1 shells `which <name>` (or the Windows equivalent via shutil.which).
    Antigravity has no MCP server yet, so its row is always 'not yet supported'.
    """
    return Response(
        {
            "claude_code": _agent_status("claude", supported="full"),
            "codex": _agent_status("codex", supported="best-effort"),
            "antigravity": {
                "name": "Antigravity",
                "installed": False,
                "supported": "not yet — Antigravity has not shipped an MCP server",
                "binary_on_path": False,
            },
        }
    )


def _agent_status(binary: str, *, supported: str) -> dict:
    on_path = shutil.which(binary) is not None
    return {
        "name": binary,
        "installed": on_path,
        "binary_on_path": on_path,
        "supported": supported,
        "configured_project": _repo_root().joinpath(".mcp.json").exists()
        if binary == "claude"
        else False,
    }


# ────────────────────────────────────────────────────────────────────
# /api/mcp/run-monthly/
# ────────────────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mcp_run_monthly(request):
    """Kick the monthly Top-50 job in the background.

    Runs `manage.py run_monthly_top_50` inside Django's call_command on a
    background thread so the request returns within a few hundred ms. The
    schedule_tracker captures the start/end state, so the UI's polling on
    /api/schedules/ shows the run move from `running` → `succeeded`/`failed`.
    """
    month = (request.data.get("month") or "").strip() or datetime.now(
        timezone.utc
    ).strftime("%Y-%m")
    strategy = (request.data.get("strategy") or "auto").strip()
    if strategy not in ("auto", "claude_code", "python"):
        return Response(
            {"error": f"invalid strategy {strategy!r}"},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    def _run() -> None:
        from django.db import connection

        connection.close()
        try:
            from django.core.management import call_command

            call_command("run_monthly_top_50", month=month, strategy=strategy)
        except Exception:
            logger.exception("mcp_run_monthly: background job failed")

    threading.Thread(target=_run, daemon=True).start()
    return Response(
        {"queued": True, "month": month, "strategy": strategy},
        status=drf_status.HTTP_202_ACCEPTED,
    )


# ────────────────────────────────────────────────────────────────────
# /api/schedules/
# ────────────────────────────────────────────────────────────────────


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def schedules_status(request):
    """Snapshot of every registered schedule + its recent runs."""
    from apps.core.services.schedule_tracker import get_status_for_ui

    return Response({"schedules": get_status_for_ui()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def schedule_run_now(request, task_name: str):
    """Manually fire the registered callable for a given schedule."""
    from apps.core.services.schedule_tracker import _REGISTRY

    spec = _REGISTRY.get(task_name)
    if spec is None:
        return Response(
            {"error": f"no registered schedule named {task_name!r}"},
            status=drf_status.HTTP_404_NOT_FOUND,
        )

    def _run() -> None:
        from django.db import connection

        connection.close()
        try:
            spec.fire_callable(datetime.now(timezone.utc))
        except Exception:
            logger.exception("schedule_run_now: %s failed", task_name)

    threading.Thread(target=_run, daemon=True).start()
    return Response(
        {"queued": True, "task_name": task_name}, status=drf_status.HTTP_202_ACCEPTED
    )


# ────────────────────────────────────────────────────────────────────
# /api/reports/monthly/  — list + read the markdown reports
# ────────────────────────────────────────────────────────────────────


_MONTHLY_REPORT_GLOB = "monthly-suggestions-*.md"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def monthly_reports_list(request):
    """List every `monthly-suggestions-YYYY-MM.md` under docs/reports/."""
    reports_dir = _repo_root() / "docs" / "reports"
    if not reports_dir.exists():
        return Response({"reports": []})
    items: list[dict] = []
    for path in sorted(reports_dir.glob(_MONTHLY_REPORT_GLOB), reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        # Filename pattern: monthly-suggestions-YYYY-MM.md → strip prefix + suffix.
        slug = path.stem.removeprefix("monthly-suggestions-")
        items.append(
            {
                "month": slug,
                "filename": path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds"),
            }
        )
    return Response({"reports": items})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def monthly_report_read(request, month: str):
    """Return the markdown body of a single monthly report.

    `month` is the YYYY-MM slug; the actual file lives at
    `docs/reports/monthly-suggestions-<month>.md`.
    """
    if not _is_safe_month_slug(month):
        return Response(
            {"error": "invalid month slug"}, status=drf_status.HTTP_400_BAD_REQUEST
        )
    path = _repo_root() / "docs" / "reports" / f"monthly-suggestions-{month}.md"
    if not path.exists() or not path.is_file():
        raise NotFound(f"no monthly report for {month}")
    try:
        body = path.read_text(encoding="utf-8")
    except OSError as exc:
        return Response(
            {"error": str(exc)}, status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return Response({"month": month, "filename": path.name, "body": body})


def _is_safe_month_slug(s: str) -> bool:
    """Defensive check: only YYYY-MM gets past us, no path traversal."""
    if not s or len(s) != 7 or s[4] != "-":
        return False
    try:
        datetime.strptime(s, "%Y-%m")
    except ValueError:
        return False
    return True


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _repo_root() -> Path:
    """Best guess at the repo root for both Docker and local-dev runs.

    Inside the backend container the repo is mounted at /app; locally, this
    file lives at backend/apps/core/views_mcp.py so we walk up four levels.
    """
    candidate = Path("/app")
    if candidate.exists() and (candidate / ".mcp.json").exists():
        return candidate
    here = Path(__file__).resolve()
    for parent in (here.parents[3], here.parents[4] if len(here.parents) > 4 else None):
        if parent and (parent / ".mcp.json").exists():
            return parent
    # Fallback: BASE_DIR from settings (per backend/config/settings/*).
    return Path(getattr(settings, "BASE_DIR", here.parents[3])).resolve()


def _has_python_pkg(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False
    except Exception:  # noqa: BLE001  # noqa: forbidden-pattern silent-except  # justification: package-detection probe runs at MCP server boot for every optional dependency; some packages (e.g. faiss, torch) do non-trivial work at import time that can fail in sandboxes / minimal containers, but a probe failure must just answer "not installed" and never crash the MCP introspection endpoint.
        return False
