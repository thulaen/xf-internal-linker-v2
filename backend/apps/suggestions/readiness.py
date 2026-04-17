"""
Phase SR — Suggestion Readiness Gate aggregator.

Assembles a single go/no-go verdict for the Review page: "are the
suggestions we're about to show the operator backed by fresh,
trustworthy data, or is the pipeline still warming up?"

Reuses every existing health-check and AppSetting — NO new detection
logic. The plan explicitly listed each source of truth; this module is
just the mapping layer that turns them into a short list of
plain-English prerequisites with deduped root-cause grouping.

Shape of each prerequisite dict:

    {
        "id": str,              # stable id for client dedup
        "category": str,        # "signals" | "embeddings" | "meta" | "external" | ...
        "name": str,            # human title
        "status": str,          # "ready" | "running" | "stale" | "blocked" | "not_configured"
        "plain_english": str,   # one-sentence operator-facing explanation
        "next_step": str,       # empty string if nothing needed, else the fix
        "progress": float,      # 0.0..1.0 when applicable; else 1.0 when ready
        "affects": list[str],   # dependent categories this one gates (root-cause grouping)
    }
"""

from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from django.db.models import Max
from django.utils import timezone

from apps.pipeline.services.task_lock import get_active_locks

# ── Freshness windows ────────────────────────────────────────────────
# Deliberately generous so transient noise doesn't flip the gate.
_MATH_MAX_STALE_MINUTES = 60
_ATTRIBUTION_MAX_STALE_HOURS = 6
_COOCCURRENCE_MAX_STALE_HOURS = 24


# ─────────────────────────────────────────────────────────────────────
# individual prerequisite builders — one per category the plan listed.
# each returns either a dict (prerequisite) or None when the category
# is not relevant on this deployment (e.g. matomo not configured).
# ─────────────────────────────────────────────────────────────────────


def _prereq_signals() -> dict:
    """Ranking signals — running / queued via Phase SEQ lock namespace."""
    locks = get_active_locks()
    holder = locks.get("signal")
    if not holder:
        return {
            "id": "signals",
            "category": "signals",
            "name": "Ranking signals",
            "status": "ready",
            "plain_english": "No signal computes in flight.",
            "next_step": "",
            "progress": 1.0,
            "affects": [],
        }
    # Redis lock owner value looks like "compute_signal_x:<uuid>:<ts>"
    raw = str(holder)
    task_name = raw.split(":", 1)[0] if ":" in raw else raw
    return {
        "id": "signals",
        "category": "signals",
        "name": "Ranking signals",
        "status": "running",
        "plain_english": (
            f"Signal compute in flight: {task_name}. Suggestions may "
            f"drift while this finishes."
        ),
        "next_step": "Wait for the current signal to complete.",
        "progress": 0.5,
        "affects": [],
    }


def _prereq_math() -> dict:
    """Ranking math / weight application — AppSetting last_math_refreshed_at."""
    from apps.core.models import AppSetting

    last = _get_setting_datetime(AppSetting, "system.last_math_refreshed_at")
    if last is None:
        return {
            "id": "math",
            "category": "math",
            "name": "Ranking math",
            "status": "stale",
            "plain_english": (
                "Ranking math has never been refreshed; suggestions may reflect "
                "older weights."
            ),
            "next_step": "Trigger a pipeline run so the math snapshot populates.",
            "progress": 0.0,
            "affects": [],
        }
    age = timezone.now() - last
    if age <= timedelta(minutes=_MATH_MAX_STALE_MINUTES):
        return {
            "id": "math",
            "category": "math",
            "name": "Ranking math",
            "status": "ready",
            "plain_english": f"Ranking math refreshed {_humanize_ago(age)}.",
            "next_step": "",
            "progress": 1.0,
            "affects": [],
        }
    return {
        "id": "math",
        "category": "math",
        "name": "Ranking math",
        "status": "stale",
        "plain_english": (
            f"Ranking math last refreshed {_humanize_ago(age)} — older than "
            f"our {_MATH_MAX_STALE_MINUTES}-min freshness window."
        ),
        "next_step": "Run a pipeline pass so ranking math is recomputed.",
        "progress": 0.0,
        "affects": [],
    }


def _prereq_embeddings() -> dict:
    """Embeddings complete for in-scope content."""
    try:
        from apps.content.models import ContentItem

        total_queryset = ContentItem.objects.all()
        total = total_queryset.count()
        if total == 0:
            return {
                "id": "embeddings",
                "category": "embeddings",
                "name": "Embeddings",
                "status": "ready",
                "plain_english": "No in-scope content yet.",
                "next_step": "",
                "progress": 1.0,
                "affects": [],
            }
        missing = total_queryset.filter(embedding__isnull=True).count()
        if missing == 0:
            return {
                "id": "embeddings",
                "category": "embeddings",
                "name": "Embeddings",
                "status": "ready",
                "plain_english": f"All {total} in-scope items are embedded.",
                "next_step": "",
                "progress": 1.0,
                "affects": [],
            }
        pct_done = (total - missing) / total
        return {
            "id": "embeddings",
            "category": "embeddings",
            "name": "Embeddings",
            "status": "running" if pct_done >= 0.5 else "blocked",
            "plain_english": (
                f"Embeddings in progress — {total - missing:,} of {total:,} items "
                f"done ({pct_done:.0%})."
            ),
            "next_step": (
                "Let the embedding worker drain; suggestions may be thin for "
                "items still waiting."
            ),
            "progress": pct_done,
            "affects": [],
        }
    except Exception as exc:  # noqa: BLE001 — never let this crash the gate
        return {
            "id": "embeddings",
            "category": "embeddings",
            "name": "Embeddings",
            "status": "blocked",
            "plain_english": f"Could not read embeddings state: {exc.__class__.__name__}.",
            "next_step": "Check backend logs for ContentItem read errors.",
            "progress": 0.0,
            "affects": [],
        }


def _prereq_meta() -> dict:
    """C++ hot paths + meta-algorithms — reuses check_native_scoring."""
    from apps.diagnostics import health as dh

    state, explanation, next_step, _metadata = dh.check_native_scoring()
    if state == "healthy":
        return {
            "id": "meta",
            "category": "meta",
            "name": "C++ hot paths / meta-algorithms",
            "status": "ready",
            "plain_english": "Native scoring modules are healthy.",
            "next_step": "",
            "progress": 1.0,
            "affects": [],
        }
    return {
        "id": "meta",
        "category": "meta",
        "name": "C++ hot paths / meta-algorithms",
        "status": "blocked" if state in ("down", "error") else "stale",
        "plain_english": explanation,
        "next_step": next_step,
        "progress": 0.0,
        "affects": [],
    }


def _prereq_slate() -> dict:
    from apps.diagnostics import health as dh

    state, explanation, next_step, _metadata = dh.check_slate_diversity_runtime()
    if state == "healthy":
        return {
            "id": "slate_diversity",
            "category": "meta",
            "name": "Slate diversity runtime",
            "status": "ready",
            "plain_english": "Slate diversity runtime is healthy.",
            "next_step": "",
            "progress": 1.0,
            "affects": [],
        }
    return {
        "id": "slate_diversity",
        "category": "meta",
        "name": "Slate diversity runtime",
        "status": "blocked" if state in ("down", "error") else "stale",
        "plain_english": explanation,
        "next_step": next_step,
        "progress": 0.0,
        "affects": [],
    }


def _prereq_attribution() -> dict:
    from apps.core.models import AppSetting

    last = _get_setting_datetime(AppSetting, "system.last_attribution_run_at")
    if last is None:
        return {
            "id": "attribution",
            "category": "meta",
            "name": "Attribution engine",
            "status": "stale",
            "plain_english": "Attribution engine has never run on this install.",
            "next_step": "Trigger the attribution task to compute initial scores.",
            "progress": 0.0,
            "affects": [],
        }
    age = timezone.now() - last
    ok = age <= timedelta(hours=_ATTRIBUTION_MAX_STALE_HOURS)
    return {
        "id": "attribution",
        "category": "meta",
        "name": "Attribution engine",
        "status": "ready" if ok else "stale",
        "plain_english": (
            f"Attribution last computed {_humanize_ago(age)}."
            if ok
            else f"Attribution last computed {_humanize_ago(age)} — older than "
            f"{_ATTRIBUTION_MAX_STALE_HOURS}h freshness window."
        ),
        "next_step": "" if ok else "Recompute attribution from the Mission Critical tile.",
        "progress": 1.0 if ok else 0.0,
        "affects": [],
    }


def _prereq_cooccurrence() -> dict:
    try:
        from apps.cooccurrence.models import SessionCooccurrencePair

        latest = SessionCooccurrencePair.objects.aggregate(m=Max("updated_at"))["m"]
        if latest is None:
            return {
                "id": "cooccurrence",
                "category": "meta",
                "name": "Cooccurrence",
                "status": "stale",
                "plain_english": "Cooccurrence table is empty.",
                "next_step": "Run the cooccurrence rebuild task.",
                "progress": 0.0,
                "affects": [],
            }
        age = timezone.now() - latest
        ok = age <= timedelta(hours=_COOCCURRENCE_MAX_STALE_HOURS)
        return {
            "id": "cooccurrence",
            "category": "meta",
            "name": "Cooccurrence",
            "status": "ready" if ok else "stale",
            "plain_english": (
                f"Cooccurrence pairs refreshed {_humanize_ago(age)}."
                if ok
                else f"Cooccurrence pairs last refreshed {_humanize_ago(age)}; older "
                f"than {_COOCCURRENCE_MAX_STALE_HOURS}h."
            ),
            "next_step": "" if ok else "Rebuild cooccurrence from the Mission Critical tile.",
            "progress": 1.0 if ok else 0.0,
            "affects": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "cooccurrence",
            "category": "meta",
            "name": "Cooccurrence",
            "status": "blocked",
            "plain_english": f"Could not read cooccurrence state: {exc.__class__.__name__}.",
            "next_step": "Check backend logs.",
            "progress": 0.0,
            "affects": [],
        }


def _prereq_external(source_id: str, name: str, checker) -> dict | None:
    """GSC / GA4 / Matomo data flows — returns None when not configured."""
    state, explanation, next_step, _meta = checker()
    if state == "not_configured":
        return None  # not on this deployment, don't surface as a blocker
    return {
        "id": source_id,
        "category": "external",
        "name": name,
        "status": "ready" if state == "healthy" else "stale",
        "plain_english": explanation,
        "next_step": next_step,
        "progress": 1.0 if state == "healthy" else 0.0,
        "affects": [],
    }


def _prereq_pipeline_gate() -> dict:
    """Wraps PipelineGateView's can_run decision into a prerequisite row."""
    try:
        # PipelineGateView's blocker logic lives inline in the view; mirror
        # the minimal subset here rather than circularly importing the view.
        from apps.health.services import (
            check_celery_health,
            check_gpu_faiss_health,
            check_ml_models_health,
        )

        blockers: list[str] = []
        for result in (
            check_gpu_faiss_health(),
            check_ml_models_health(),
            check_celery_health(),
        ):
            # ServiceHealthResult exposes `.status` and `.issue_description`
            # / `.status_label`. `healthy` is the canonical pass value.
            status = getattr(result, "status", None)
            if status and status != "healthy":
                label = (
                    getattr(result, "service_name", "")
                    or getattr(result, "service_key", "")
                    or "service"
                )
                detail = (
                    getattr(result, "issue_description", "")
                    or getattr(result, "status_label", "")
                    or status
                )
                blockers.append(f"{label}: {detail}")
        if not blockers:
            return {
                "id": "pipeline_gate",
                "category": "pipeline",
                "name": "Pipeline gate",
                "status": "ready",
                "plain_english": "Pipeline can run — GPU, models, and Celery all healthy.",
                "next_step": "",
                "progress": 1.0,
                "affects": [],
            }
        return {
            "id": "pipeline_gate",
            "category": "pipeline",
            "name": "Pipeline gate",
            "status": "blocked",
            "plain_english": "Pipeline is blocked: " + " · ".join(blockers[:3]),
            "next_step": "Resolve the blockers listed on the Diagnostics page.",
            "progress": 0.0,
            # Root-cause: a blocked pipeline gate also invalidates signals,
            # math, meta, and embeddings because they all rely on it.
            "affects": ["signals", "math", "meta", "embeddings"],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "pipeline_gate",
            "category": "pipeline",
            "name": "Pipeline gate",
            "status": "blocked",
            "plain_english": f"Could not evaluate pipeline gate: {exc.__class__.__name__}.",
            "next_step": "Check backend logs.",
            "progress": 0.0,
            "affects": ["signals", "math", "meta", "embeddings"],
        }


# ─────────────────────────────────────────────────────────────────────
# top-level assembler + dedup
# ─────────────────────────────────────────────────────────────────────


def assemble_prerequisites() -> list[dict]:
    """Build the full prerequisite list with root-cause dedup applied.

    Dedup rule from the plan:
      If the pipeline gate is blocking, its `affects` list captures the
      dependent categories (signals / math / meta / embeddings). We hide
      the dependent rows that share the root cause so the operator sees
      one explanation, not five restatements of "Redis is down".
    """
    from apps.diagnostics import health as dh

    raw: list[dict] = []
    raw.append(_prereq_pipeline_gate())
    raw.append(_prereq_signals())
    raw.append(_prereq_math())
    raw.append(_prereq_embeddings())
    raw.append(_prereq_meta())
    raw.append(_prereq_slate())
    raw.append(_prereq_attribution())
    raw.append(_prereq_cooccurrence())
    # External data-source prerequisites — silently omitted when
    # not_configured so we don't clutter the panel with "N/A" rows.
    for item in (
        _prereq_external("gsc", "Google Search Console", dh.check_gsc),
        _prereq_external("ga4", "Google Analytics 4", dh.check_ga4),
        _prereq_external("matomo", "Matomo", dh.check_matomo),
    ):
        if item is not None:
            raw.append(item)

    # Root-cause dedup: if any row is `blocked` AND has `affects`, hide
    # the affected rows from the flat list. The root's `affects` field
    # tells the UI which dependents to display collapsed under the root.
    blocking_roots = [p for p in raw if p["status"] == "blocked" and p.get("affects")]
    suppressed: set[str] = set()
    for root in blocking_roots:
        for cat in root["affects"]:
            suppressed.add(cat)

    deduped: list[dict] = []
    for p in raw:
        # Never suppress the root itself.
        if p.get("affects"):
            deduped.append(p)
            continue
        if p["category"] in suppressed:
            continue
        deduped.append(p)
    return deduped


def compute_readiness_payload() -> dict:
    """Top-level response the SuggestionReadinessView returns.

    Keeps the shape the plan specified:
        { ready, prerequisites, blocking, updated_at }
    """
    prereqs = assemble_prerequisites()
    not_ready = [p for p in prereqs if p["status"] != "ready"]
    return {
        "ready": len(not_ready) == 0,
        "prerequisites": prereqs,
        "blocking": not_ready,
        "updated_at": timezone.now().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────


def _get_setting_datetime(AppSettingModel, key: str):
    """Return a datetime parsed from AppSetting value, or None if absent/invalid."""
    from datetime import datetime

    row = AppSettingModel.objects.filter(key=key).first()
    if row is None or not row.value:
        return None
    raw = str(row.value).strip().strip('"')
    try:
        # Accept both "...+00:00" and "...Z" formats.
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _humanize_ago(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s ago"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m ago"
    if total_seconds < 86400:
        return f"{total_seconds // 3600}h ago"
    return f"{total_seconds // 86400}d ago"


__all__ = [
    "assemble_prerequisites",
    "compute_readiness_payload",
]
