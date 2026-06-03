from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess  # nosec B404
import time
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request
import zlib

from django.conf import settings
from django.core.management.base import CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, FindBugsLearnedLesson
from apps.auto_issues.services.dedup import upsert_dedup


logger = logging.getLogger(__name__)

ARTIFACT_LIMIT_BYTES = 1_073_741_824
RETENTION_DAYS = 8
DEFAULT_ARTIFACT_ROOT = Path("/tmp/xf-findbugs-artifacts")  # nosec B108
SMOLLM2_MODEL_NAME = "SmolLM2-1.7B-Instruct Q4_K_S"
SMOLLM2_TIMEOUT_SECONDS = 60
SMOLLM2_OUTPUT_LIMIT = 8_192
DEFAULT_SMOLLM2_SERVER_URL = "http://findbugs-model-server:8080"
VICTORIAMETRICS_URL = os.environ.get("VICTORIAMETRICS_URL", "http://vmsingle:8428")
FINDBUGS_EMBEDDING_QUEUE_COMFORT_LIMIT = int(
    os.environ.get("FINDBUGS_EMBEDDING_QUEUE_COMFORT_LIMIT", "0")
)
LEVEL_A_STATUS = {
    "statement": 100,
    "decision": 100,
    "mcdc": 100,
    "object_code": 100,
    "mutation": 100,
}
PROTECTED_ROOTS = (
    Path("/"),
    Path("/repo"),
    Path("/app"),
    Path("/opt/xf/compiled"),
)


@dataclass(frozen=True)
class ArtifactPruneResult:
    deleted_files: int
    deleted_bytes: int
    remaining_bytes: int
    root: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "deleted_files": self.deleted_files,
            "deleted_bytes": self.deleted_bytes,
            "remaining_bytes": self.remaining_bytes,
            "root": self.root,
        }


def build_findbugs_summary(root: Path | None = None) -> dict[str, Any]:
    issues = _findbugs_issue_queryset()
    open_count = issues.exclude(status=AutoIssue.STATUS_RESOLVED).count()
    closed_count = issues.filter(status=AutoIssue.STATUS_RESOLVED).count()
    return {
        "counts": {"open": open_count, "closed": closed_count},
        "severity": _severity_counts(issues),
        "agents": _contribution_counts(issues, "resolved_by"),
        "models": _model_counts(issues),
        "last_run_at": _last_seen(issues),
        "artifacts": artifact_state(root=root),
        "model": model_state(root=root),
        "model_batch": model_batch_state(root=root),
        "level_a": dict(LEVEL_A_STATUS),
    }


def list_findbugs_findings(
    *,
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    agent: str | None = None,
    model: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    queryset = _findbugs_issue_queryset().select_related("category")
    if status:
        queryset = queryset.filter(status=status)
    if severity:
        queryset = queryset.filter(severity=severity)
    if category:
        queryset = queryset.filter(category__key=category)
    if agent:
        queryset = queryset.filter(resolved_by=agent)
    if search:
        queryset = queryset.filter(title__icontains=search) | queryset.filter(
            description__icontains=search
        )

    deduped: dict[str, AutoIssue] = {}
    ordered = queryset.order_by("-priority_score", "id")
    for issue in ordered:
        if model and _metadata(issue).get("model") != model:
            continue
        key = issue.canonical_fingerprint or issue.fingerprint or str(issue.id)
        deduped.setdefault(key, issue)
    return [_issue_payload(issue) for issue in deduped.values()]


def artifact_state(root: Path | None = None) -> dict[str, Any]:
    artifact_root = _artifact_root(root)
    return {
        "root": str(artifact_root),
        "bytes": _directory_size(artifact_root),
        "limit_bytes": ARTIFACT_LIMIT_BYTES,
        "retention_days": RETENTION_DAYS,
    }


def model_state(root: Path | None = None) -> dict[str, Any]:
    status_path = _artifact_root(root) / "model" / "latest.json"
    if not status_path.exists():
        return {
            "model": SMOLLM2_MODEL_NAME,
            "status": "unknown",
            "reason": "no_status_artifact",
        }
    try:
        parsed = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "invalid", "reason": "status_artifact_unreadable"}
    return parsed if isinstance(parsed, dict) else {"status": "invalid", "reason": "status_artifact_not_object"}


def model_batch_state(root: Path | None = None) -> dict[str, Any]:
    checkpoint = _artifact_root(root) / "model" / "batch-checkpoint.json"
    if not checkpoint.exists():
        return {"total": 0, "processed": 0, "remaining": 0, "state": "sleeping"}
    try:
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"total": 0, "processed": 0, "remaining": 0, "state": "invalid"}
    progress = payload.get("progress", {})
    if not isinstance(progress, dict):
        return {"total": 0, "processed": 0, "remaining": 0, "state": "invalid"}
    return {
        "total": int(progress.get("total") or 0),
        "processed": int(progress.get("processed") or 0),
        "remaining": int(progress.get("remaining") or 0),
        "state": str(progress.get("state") or payload.get("status") or "sleeping"),
        "updated_at": payload.get("updated_at"),
    }


def prune_findbugs_artifacts(
    *, root: Path | None = None, now: float | None = None
) -> dict[str, Any]:
    artifact_root = _artifact_root(root)
    _refuse_protected_root(artifact_root)
    timestamp = time.time() if now is None else now
    artifact_root.mkdir(parents=True, exist_ok=True)

    deleted_files = 0
    deleted_bytes = 0
    cutoff = timestamp - (RETENTION_DAYS * 24 * 60 * 60)
    for file_path in _iter_files(artifact_root):
        if file_path.stat().st_mtime < cutoff:
            size = file_path.stat().st_size
            file_path.unlink()
            deleted_files += 1
            deleted_bytes += size

    while _directory_size(artifact_root) > ARTIFACT_LIMIT_BYTES:
        oldest = min(_iter_files(artifact_root), key=lambda path: path.stat().st_mtime)
        size = oldest.stat().st_size
        oldest.unlink()
        deleted_files += 1
        deleted_bytes += size

    result = ArtifactPruneResult(
        deleted_files=deleted_files,
        deleted_bytes=deleted_bytes,
        remaining_bytes=_directory_size(artifact_root),
        root=str(artifact_root),
    )
    return result.as_dict()


def run_findbugs_scan() -> dict[str, Any]:
    binary = _find_speccheck_binary()
    if binary is None:
        issue = file_findbugs_health_issue(
            reason="scanner binary unavailable",
            detail="FindBugs could not find the compiled speccheck binary.",
            severity=AutoIssue.SEVERITY_HIGH,
        )
        return {"status": "blocked", "autoissue": issue.id}

    root = _artifact_root()
    root.mkdir(parents=True, exist_ok=True)
    model_status = _removed_smollm2_status(root=root)
    report_path = root / f"findbugs-{timezone.now().strftime('%Y%m%dT%H%M%SZ')}.json"
    try:
        report = _run_speccheck_findbugs(binary)
    except CommandError as exc:
        issue = file_findbugs_health_issue(
            reason="scanner failed",
            detail=str(exc)[-1000:] or "speccheck find-bugs exited with an error.",
            severity=AutoIssue.SEVERITY_HIGH,
        )
        return {"status": "failed", "autoissue": issue.id, "model": model_status}
    report["metadata"].update(_findbugs_report_metadata(model_status, report))
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    imported = _import_findbugs_report(report_path)
    return {
        "status": "ok",
        "report": str(report_path),
        "model": model_status,
        "imported": imported,
    }


def import_latest_findbugs_report(root: Path | None = None) -> dict[str, Any]:
    artifact_root = _artifact_root(root)
    reports = sorted(artifact_root.glob("*.json"), key=lambda path: path.stat().st_mtime)
    if not reports:
        issue = file_findbugs_health_issue(
            reason="latest report missing",
            detail="FindBugs import was requested, but no report JSON exists.",
            severity=AutoIssue.SEVERITY_MEDIUM,
        )
        return {"status": "missing", "autoissue": issue.id}
    result = _import_findbugs_report(reports[-1])
    return {"status": "ok", **result}


def _import_findbugs_report(report_path: Path) -> dict[str, int]:
    from apps.auto_issues.services.rust_findings import import_rust_report

    result = import_rust_report(report_path)
    return {
        "created": result.created,
        "updated": result.updated,
        "stale_resolved": result.stale_resolved,
    }


def refresh_findbugs_knowledge(root: Path | None = None) -> dict[str, Any]:
    knowledge_root = _artifact_root(root) / "knowledge"
    knowledge_root.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "generated_at": timezone.now().isoformat(),
        "open": AutoIssue.objects.filter(
            source=AutoIssue.SOURCE_RUST_DEFECT,
            status=AutoIssue.STATUS_OPEN,
        ).count(),
        "closed": AutoIssue.objects.filter(
            source=AutoIssue.SOURCE_RUST_DEFECT,
            status=AutoIssue.STATUS_RESOLVED,
        ).count(),
    }
    target = knowledge_root / "latest.json.gz"
    target.write_bytes(gzip.compress(json.dumps(snapshot, sort_keys=True).encode("utf-8")))
    return {"status": "ok", "artifact": str(target)}


def session_start_findbugs_check() -> dict[str, Any]:
    state = artifact_state()
    if state["bytes"] > ARTIFACT_LIMIT_BYTES:
        issue = file_findbugs_health_issue(
            reason="artifact cap breached",
            detail="FindBugs artifacts exceed the 1 GB cap.",
            severity=AutoIssue.SEVERITY_HIGH,
        )
        return {"status": "degraded", "autoissue": issue.id, "artifacts": state}
    return {"status": "ok", "artifacts": state}


def maybe_run_smollm2_advisory(
    *,
    root: Path | None = None,
    embedding_busy: Callable[[], bool] | None = None,
    runner_path: Path | None = None,
    model_path: Path | None = None,
    server_url: str | None = None,
    prompt: str = "Find suspicious bug patterns. Return compact JSON only.",
) -> dict[str, Any]:
    busy = embedding_busy() if embedding_busy is not None else _embeddings_are_busy()
    resource_comfort = _findbugs_model_resource_comfort(embedding_busy=busy)

    server = _configured_smollm2_server(server_url)
    if server:
        return _run_smollm2_server_advisory(
            server,
            prompt,
            root=root,
            resource_comfort=resource_comfort,
        )

    runner = _configured_smollm2_runner(runner_path)
    model = _configured_smollm2_model(model_path)
    if runner is None or model is None:
        issue = file_findbugs_health_issue(
            reason="model runner or GGUF missing",
            detail=(
                "FindBugs tried to run the always-on SmolLM2 advisory model, "
                "but the llama.cpp runner or SmolLM2 GGUF file is not configured. "
                "Install both paths so model-assisted bug search is actually running."
            ),
            severity=AutoIssue.SEVERITY_HIGH,
        )
        payload = _smollm2_status_payload(
            "unavailable",
            "runner_or_model_missing",
            issue.id,
            resource_comfort=resource_comfort,
        )
        artifact = _write_smollm2_status(payload, root=root)
        return {
            "status": "unavailable",
            "reason": "runner_or_model_missing",
            "artifact": str(artifact),
            "autoissue": issue.id,
            "resource_comfort": resource_comfort,
        }

    command = _smollm2_runner_command(runner, model, prompt)
    try:
        completed = subprocess.run(  # nosec B603
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=SMOLLM2_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return _smollm2_runner_failure(
            "runner_timeout",
            "FindBugs SmolLM2 local runner did not exit before the timeout.",
            returncode=-1,
            stdout=_subprocess_text(exc.output),
            stderr=_subprocess_text(exc.stderr),
            root=root,
            resource_comfort=resource_comfort,
        )
    except OSError as exc:
        return _smollm2_runner_failure(
            "runner_failed",
            f"FindBugs SmolLM2 local runner could not start: {str(exc)[:300]}",
            returncode=-1,
            stdout="",
            stderr=str(exc),
            root=root,
            resource_comfort=resource_comfort,
        )
    output_payload = _smollm2_output_payload(completed.returncode, completed.stdout, completed.stderr)
    artifact = _write_smollm2_output(output_payload, root=root, resource_comfort=resource_comfort)
    if completed.returncode != 0:
        return _smollm2_runner_failure(
            "runner_failed",
            (
                "FindBugs SmolLM2 local runner exited with a nonzero status. "
                f"returncode={completed.returncode}"
            ),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            root=root,
            resource_comfort=resource_comfort,
        )
    return {
        "status": "ok",
        "reason": "runner_completed",
        "artifact": str(artifact),
        "resource_comfort": resource_comfort,
    }


def run_smollm2_batch_advisory(
    *,
    max_items: int = 25,
    root: Path | None = None,
) -> dict[str, Any]:
    return _removed_smollm2_status(root=root)


def _run_removed_smollm2_batch_advisory_old(
    *,
    max_items: int = 25,
    root: Path | None = None,
) -> dict[str, Any]:
    batch_root = _artifact_root(root) / "model"
    batch_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = batch_root / "batch-checkpoint.json"
    if (batch_root / "pause").exists():
        return {"status": "paused", "reason": "pause_file_present"}
    if _embeddings_are_busy():
        _write_batch_checkpoint(
            checkpoint_path,
            status="sleeping",
            processed_fingerprints=_checkpoint_fingerprints(checkpoint_path),
            total=0,
            processed=0,
            remaining=0,
        )
        return {"status": "skipped", "reason": "embeddings_busy"}

    candidates = list(
        AutoIssue.objects.filter(
            source=AutoIssue.SOURCE_RUST_DEFECT,
        )
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .order_by("-priority_score", "id")[: max_items * 4]
    )
    if not candidates:
        return {"status": "skipped", "reason": "no_findbugs_items"}

    processed_fingerprints = _checkpoint_fingerprints(checkpoint_path)
    deduped_candidates = _dedupe_findbugs_batch(candidates)
    eligible = [
        issue for issue in deduped_candidates
        if _issue_batch_fingerprint(issue) not in processed_fingerprints
    ][:max_items]
    if not eligible:
        progress = _batch_progress(
            total=len(deduped_candidates),
            processed=len(processed_fingerprints),
            state="complete",
        )
        _write_batch_checkpoint(
            checkpoint_path,
            status="complete",
            processed_fingerprints=processed_fingerprints,
            total=progress["total"],
            processed=progress["processed"],
            remaining=progress["remaining"],
        )
        return {"status": "skipped", "reason": "already_processed", "progress": progress}

    deduped = _fit_batch_to_context(eligible)
    if not deduped:
        issue = file_findbugs_health_issue(
            reason="item exceeds model context",
            detail=(
                "FindBugs model batch found an item that cannot fit inside the "
                "configured model context window without truncation. Increase "
                "FINDBUGS_MODEL_CONTEXT_CHARS or reduce the per-item evidence shape."
            ),
            severity=AutoIssue.SEVERITY_MEDIUM,
        )
        return {
            "status": "blocked",
            "reason": "item_exceeds_model_context",
            "autoissue": issue.id,
        }

    progress = _batch_progress(
        total=len(deduped_candidates),
        processed=len(processed_fingerprints),
        state="processing",
    )
    _write_batch_checkpoint(
        checkpoint_path,
        status="processing",
        processed_fingerprints=processed_fingerprints,
        total=progress["total"],
        processed=progress["processed"],
        remaining=progress["remaining"],
    )
    prompt = _findbugs_batch_prompt(deduped)
    result = maybe_run_smollm2_advisory(prompt=prompt)
    if result.get("status") == "ok":
        _mark_model_batch_processed(deduped, result)
        processed_fingerprints = [
            *processed_fingerprints,
            *[_issue_batch_fingerprint(issue) for issue in deduped],
        ]
    final_progress = _batch_progress(
        total=len(deduped_candidates),
        processed=len(processed_fingerprints),
        state="complete" if result.get("status") == "ok" else "failed",
    )
    _write_batch_checkpoint(
        checkpoint_path,
        status=final_progress["state"],
        processed_fingerprints=processed_fingerprints,
        total=final_progress["total"],
        processed=final_progress["processed"],
        remaining=final_progress["remaining"],
    )
    return {
        "status": str(result.get("status", "unknown")),
        "reason": result.get("reason", ""),
        "processed": len(deduped),
        "deduped_from": len(candidates),
        "artifact": result.get("artifact"),
        "progress": final_progress,
    }


def _dedupe_findbugs_batch(issues: list[AutoIssue]) -> list[AutoIssue]:
    deduped: dict[str, AutoIssue] = {}
    for issue in issues:
        key = issue.canonical_fingerprint or issue.fingerprint or str(issue.id)
        deduped.setdefault(key, issue)
    return list(deduped.values())


def _fit_batch_to_context(issues: list[AutoIssue]) -> list[AutoIssue]:
    selected: list[AutoIssue] = []
    for issue in issues:
        candidate = [*selected, issue]
        if len(_findbugs_batch_prompt(candidate)) > _model_prompt_budget_chars():
            break
        selected = candidate
    return selected


def _findbugs_batch_prompt(issues: list[AutoIssue]) -> str:
    rows = [_batch_prompt_row(issue) for issue in issues]
    return (
        "FindBugs already confirmed these deterministic bug findings. "
        "Review this deduped batch once, suggest prioritization notes, and "
        "return compact JSON only.\n"
        + json.dumps(rows, sort_keys=True)
    )


def _batch_prompt_row(issue: AutoIssue) -> dict[str, Any]:
    detail = _metadata(issue)
    return {
            "id": issue.id,
            "fingerprint": issue.canonical_fingerprint or issue.fingerprint,
            "title": issue.title,
            "severity": issue.severity,
            "file": (issue.affected_files or [""])[0],
            "message": detail.get("message", ""),
            "suggested_fix": detail.get("suggested_fix", ""),
            "truncated": False,
    }


def _model_prompt_budget_chars() -> int:
    context = int(os.environ.get("FINDBUGS_MODEL_CONTEXT_CHARS", "1536"))
    safety = int(os.environ.get("FINDBUGS_MODEL_CONTEXT_SAFETY_CHARS", "256"))
    return max(256, context - safety)


def _mark_model_batch_processed(issues: list[AutoIssue], result: dict[str, Any]) -> None:
    notes_by_fingerprint = {
        str(note.get("fingerprint")): note
        for note in result.get("notes", [])
        if isinstance(note, dict)
    }
    for issue in issues:
        detail = _metadata(issue)
        fingerprint = _issue_batch_fingerprint(issue)
        detail["model_batch"] = {
            "model": SMOLLM2_MODEL_NAME,
            "status": result.get("status"),
            "reason": result.get("reason"),
            "artifact": result.get("artifact"),
            "notes": notes_by_fingerprint.get(fingerprint, {}),
            "processed_at": timezone.now().isoformat(),
        }
        issue.description = json.dumps(detail, sort_keys=True)
        issue.save(update_fields=["description"])


def _issue_batch_fingerprint(issue: AutoIssue) -> str:
    return str(issue.canonical_fingerprint or issue.fingerprint or issue.id)


def _checkpoint_fingerprints(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("processed_fingerprints", [])
    return [str(row) for row in rows] if isinstance(rows, list) else []


def _batch_progress(
    *,
    total: int,
    processed: int,
    state: str,
) -> dict[str, Any]:
    processed = min(processed, total)
    return {
        "total": total,
        "processed": processed,
        "remaining": max(0, total - processed),
        "state": state,
    }


def _write_batch_checkpoint(
    path: Path,
    *,
    status: str,
    processed_fingerprints: list[str],
    total: int,
    processed: int,
    remaining: int,
) -> None:
    payload = {
        "status": status,
        "processed_fingerprints": processed_fingerprints,
        "progress": {
            "total": total,
            "processed": processed,
            "remaining": remaining,
            "state": status,
        },
        "updated_at": timezone.now().isoformat(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _removed_smollm2_status(*, root: Path | None = None) -> dict[str, Any]:
    payload = _smollm2_status_payload(
        "removed",
        "operator_removed_ai_model",
        None,
        resource_comfort={"reason": "not_applicable"},
    )
    artifact = _write_smollm2_status(payload, root=root)
    return {
        "status": "removed",
        "reason": "operator_removed_ai_model",
        "artifact": str(artifact),
        "resource_comfort": payload["resource_comfort"],
    }


def _run_smollm2_server_advisory(
    server_url: str,
    prompt: str,
    *,
    root: Path | None,
    resource_comfort: dict[str, Any],
) -> dict[str, Any]:
    url = f"{server_url.rstrip('/')}/completion"
    body = json.dumps({
        "prompt": prompt,
        "n_predict": int(_setting_value("FINDBUGS_SMOLLM2_PREDICT_TOKENS") or "32"),
        "temperature": 0,
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=SMOLLM2_TIMEOUT_SECONDS) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ) as exc:
        issue = file_findbugs_health_issue(
            reason="model server unavailable",
            detail=(
                "FindBugs tried to use the warm llama.cpp SmolLM2 server, "
                f"but the request failed: {str(exc)[:300]}"
            ),
            severity=AutoIssue.SEVERITY_HIGH,
        )
        status_payload = _smollm2_status_payload(
            "failed",
            "server_unavailable",
            issue.id,
            resource_comfort=resource_comfort,
        )
        artifact = _write_smollm2_status(status_payload, root=root)
        return {
            "status": "failed",
            "reason": "server_unavailable",
            "artifact": str(artifact),
            "autoissue": issue.id,
            "resource_comfort": resource_comfort,
        }

    output_payload = _smollm2_output_payload(
        0,
        str(payload.get("content") or payload.get("response") or payload),
        "",
    )
    artifact = _write_smollm2_output(
        output_payload,
        root=root,
        resource_comfort=resource_comfort,
        reason="server_completed",
    )
    return {
        "status": "ok",
        "reason": "server_completed",
        "artifact": str(artifact),
        "resource_comfort": resource_comfort,
    }


def confirm_real_bug(*, issue_id: int, agent: str) -> dict[str, Any]:
    issue = _get_findbugs_issue(issue_id)
    issue.lessons_learned = (
        "Trap: FindBugs finding was reviewed and confirmed as a real bug. "
        "Fix shape: keep it in the normal AutoIssue fixing workflow."
    )
    issue.resolved_by = agent
    issue.save(update_fields=["lessons_learned", "resolved_by"])
    return {"status": "ok", "issue_id": issue.id, "classification": "real_bug"}


def evaluate_with_agents(*, issue_ids: list[int], agent: str) -> dict[str, Any]:
    updated = 0
    for issue in AutoIssue.objects.filter(
        id__in=issue_ids,
        source=AutoIssue.SOURCE_RUST_DEFECT,
    ):
        detail = _metadata(issue)
        detail["agent_evaluation"] = {"status": "queued", "agent": agent}
        issue.description = json.dumps(detail, sort_keys=True)
        issue.save(update_fields=["description"])
        updated += 1
    return {"status": "queued", "count": updated}


def duplicate_check(*, issue_id: int) -> dict[str, Any]:
    issue = _get_findbugs_issue(issue_id)
    fingerprint = issue.canonical_fingerprint or issue.fingerprint
    duplicate_count = AutoIssue.objects.filter(
        source=AutoIssue.SOURCE_RUST_DEFECT,
        canonical_fingerprint=fingerprint,
    ).count()
    return {"status": "ok", "duplicate_count": duplicate_count}


def regression_check(*, issue_id: int) -> dict[str, Any]:
    issue = _get_findbugs_issue(issue_id)
    lesson_count = FindBugsLearnedLesson.objects.filter(
        source_issue__canonical_fingerprint=issue.canonical_fingerprint,
    ).count()
    return {"status": "ok", "lesson_count": lesson_count}


def generate_findbugs_report() -> dict[str, Any]:
    return {
        "status": "ok",
        "summary": {
            "open": AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_RUST_DEFECT,
                status=AutoIssue.STATUS_OPEN,
            ).count(),
            "closed": AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_RUST_DEFECT,
                status=AutoIssue.STATUS_RESOLVED,
            ).count(),
            "false_positive": FindBugsLearnedLesson.objects.filter(
                classification=FindBugsLearnedLesson.CLASS_FALSE_POSITIVE,
            ).count(),
            "false_negative": FindBugsLearnedLesson.objects.filter(
                classification=FindBugsLearnedLesson.CLASS_FALSE_NEGATIVE,
            ).count(),
        },
        "source_comparison": compare_findbugs_with_observability_sources(),
    }


def compare_findbugs_with_observability_sources() -> dict[str, Any]:
    findbugs = _canonical_fingerprints(AutoIssue.SOURCE_RUST_DEFECT)
    glitchtip = _canonical_fingerprints(AutoIssue.SOURCE_GLITCHTIP)
    sonarqube = _canonical_fingerprints(AutoIssue.SOURCE_SONARQUBE)
    observed_elsewhere = glitchtip | sonarqube
    unique = sorted(findbugs - observed_elsewhere)
    return {
        "findbugs_total": len(findbugs),
        "glitchtip_overlap": len(findbugs & glitchtip),
        "sonarqube_overlap": len(findbugs & sonarqube),
        "findbugs_unique": len(unique),
        "unique_fingerprints": unique[:25],
    }


def sync_findbugs_context(root: Path | None = None) -> dict[str, Any]:
    artifact_root = _artifact_root(root) / "context"
    artifact_root.mkdir(parents=True, exist_ok=True)
    target = artifact_root / "latest.json"
    target.write_text(
        json.dumps(generate_findbugs_report()["summary"], sort_keys=True),
        encoding="utf-8",
    )
    return {"status": "ok", "artifact": str(target)}


def create_fix_task(*, issue_id: int) -> dict[str, Any]:
    issue = _get_findbugs_issue(issue_id)
    issue.status = AutoIssue.STATUS_PICKED
    issue.save(update_fields=["status"])
    return {"status": "ok", "issue_id": issue.id}


def assign_to_agent(*, issue_id: int, agent: str) -> dict[str, Any]:
    issue = _get_findbugs_issue(issue_id)
    detail = _metadata(issue)
    detail["assigned_agent"] = agent
    issue.description = json.dumps(detail, sort_keys=True)
    issue.status = AutoIssue.STATUS_PICKED
    issue.save(update_fields=["description", "status"])
    return {"status": "ok", "issue_id": issue.id, "agent": agent}


def approve_latest_lesson(*, issue_id: int, agent: str) -> dict[str, Any]:
    issue = _get_findbugs_issue(issue_id)
    lesson = issue.findbugs_lessons.order_by("-last_seen").first()
    if lesson is None:
        raise CommandError("No FindBugs learned lesson exists for this issue.")
    lesson.approved = True
    lesson.created_by = lesson.created_by or agent
    lesson.save(update_fields=["approved", "created_by", "last_seen"])
    return {"status": "ok", "issue_id": issue.id, "lesson_id": lesson.id}


def file_findbugs_health_issue(
    *, reason: str, detail: str, severity: str = AutoIssue.SEVERITY_MEDIUM
) -> AutoIssue:
    fingerprint = hashlib.sha1(
        f"findbugs-health:{reason}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    description = json.dumps(
        {"reason": reason, "detail": detail, "source": "FindBugs self-monitor"},
        sort_keys=True,
    )
    issue, _ = upsert_dedup(
        canonical=fingerprint,
        source=AutoIssue.SOURCE_RUST_DEFECT,
        external_id=f"findbugs-health:{fingerprint[:24]}",
        fingerprint=fingerprint,
        title=f"[FindBugs health] {reason}",
        description=description,
        affected_files=[],
        severity=severity,
        priority_score=95.0,
        occurrence_count=1,
        category_key="findbugs-health",
    )
    return issue


def move_issue_to_learned_lesson(
    *,
    issue_id: int,
    classification: str,
    lesson: str,
    agent: str,
) -> FindBugsLearnedLesson:
    if classification not in dict(FindBugsLearnedLesson.CLASS_CHOICES):
        raise CommandError("FindBugs lesson classification must be false_positive or false_negative.")
    issue = AutoIssue.objects.get(id=issue_id, source=AutoIssue.SOURCE_RUST_DEFECT)
    payload = {
        "classification": classification,
        "lesson": lesson,
        "bug_pattern_id": _pattern_from_title(issue.title),
        "canonical_fingerprint": issue.canonical_fingerprint,
        "affected_files": issue.affected_files,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    fingerprint = hashlib.sha256(raw).hexdigest()
    lesson_row, created = FindBugsLearnedLesson.objects.get_or_create(
        lesson_fingerprint=fingerprint,
        defaults={
            "source_issue": issue,
            "classification": classification,
            "compressed_payload": compressed,
            "uncompressed_bytes": len(raw),
            "compressed_bytes": len(compressed),
            "created_by": agent,
        },
    )
    if not created:
        lesson_row.occurrence_count += 1
        lesson_row.source_issue = issue
        lesson_row.save(update_fields=["occurrence_count", "source_issue", "last_seen"])

    issue.status = AutoIssue.STATUS_RESOLVED
    issue.resolved_at = timezone.now()
    issue.resolved_by = agent
    issue.lessons_learned = lesson
    issue.save(update_fields=["status", "resolved_at", "resolved_by", "lessons_learned"])
    return lesson_row


def _get_findbugs_issue(issue_id: int) -> AutoIssue:
    return AutoIssue.objects.get(id=issue_id, source=AutoIssue.SOURCE_RUST_DEFECT)


def _findbugs_issue_queryset():
    return AutoIssue.objects.filter(source=AutoIssue.SOURCE_RUST_DEFECT)


def _canonical_fingerprints(source: str) -> set[str]:
    return set(
        AutoIssue.objects.filter(source=source)
        .exclude(canonical_fingerprint="")
        .values_list("canonical_fingerprint", flat=True)
    )


def _severity_counts(queryset) -> dict[str, int]:
    counts = {key: 0 for key, _label in AutoIssue.SEVERITY_CHOICES}
    for issue in queryset.only("severity"):
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    return counts


def _contribution_counts(queryset, field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in queryset.exclude(**{field: ""}).only(field):
        value = getattr(issue, field, "")
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _model_counts(queryset) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in queryset.only("description"):
        model = _metadata(issue).get("model")
        if isinstance(model, str) and model:
            counts[model] = counts.get(model, 0) + 1
    return counts


def _last_seen(queryset) -> str | None:
    latest = queryset.order_by("-last_seen").only("last_seen").first()
    return latest.last_seen.isoformat() if latest else None


def _issue_payload(issue: AutoIssue) -> dict[str, Any]:
    detail = _metadata(issue)
    return {
        "id": issue.id,
        "title": issue.title,
        "status": issue.status,
        "severity": issue.severity,
        "category": issue.category.key if issue.category_id else "",
        "category_key": issue.category.key if issue.category_id else "",
        "canonical_fingerprint": issue.canonical_fingerprint,
        "bug_pattern_id": detail.get("bug_pattern_id", _pattern_from_title(issue.title)),
        "line": detail.get("line"),
        "file": (issue.affected_files or [""])[0],
        "affected_files": issue.affected_files or [],
        "confidence": detail.get("confidence", ""),
        "confirmed_by": detail.get("confirmed_by", "rust"),
        "llm_candidate": bool(detail.get("llm_candidate", False)),
        "priority_score": issue.priority_score,
        "occurrence_count": issue.occurrence_count,
        "last_seen": issue.last_seen.isoformat(),
        "resolved_by": issue.resolved_by,
        "description": issue.description,
    }


def _metadata(issue: AutoIssue) -> dict[str, Any]:
    try:
        parsed = json.loads(issue.description or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _pattern_from_title(title: str) -> str:
    if title.startswith("[") and "]" in title:
        return title[1:title.index("]")]
    return ""


def _artifact_root(root: Path | None = None) -> Path:
    if root is not None:
        return root.resolve()
    configured = getattr(settings, "FINDBUGS_ARTIFACT_ROOT", None)
    return Path(configured).resolve() if configured else DEFAULT_ARTIFACT_ROOT


def _refuse_protected_root(root: Path) -> None:
    resolved = root.resolve()
    for protected in PROTECTED_ROOTS:
        if resolved == protected.resolve():
            raise CommandError(f"Refusing to prune protected path {resolved}.")


def _directory_size(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in _iter_files(root))


def _iter_files(root: Path):
    if not root.exists():
        return iter(())
    return (path for path in root.rglob("*") if path.is_file())


def _run_speccheck_findbugs(binary: Path) -> dict[str, Any]:
    merged = _empty_findbugs_report()
    scanned = 0
    for source_path in _iter_findbugs_source_files():
        completed = subprocess.run(  # nosec B603
            [str(binary), "find-bugs", str(source_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode != 0:
            raise CommandError(
                completed.stderr[-1000:] or f"speccheck failed for {source_path}"
            )
        scanned += 1
        _merge_speccheck_report(merged, _speccheck_stdout_report(completed.stdout))
    merged["summary"]["scanned_files"] = scanned
    merged["summary"]["bug_candidate_count"] = len(merged["bug_candidates"])
    return merged


def _empty_findbugs_report() -> dict[str, Any]:
    return {
        "metadata": {},
        "parsed_behaviors": [],
        "test_case_candidates": [],
        "bug_candidates": [],
        "duplicate_warnings": [],
        "stale_record_warnings": [],
        "summary": {},
    }


def _speccheck_stdout_report(stdout: object) -> dict[str, Any]:
    if not isinstance(stdout, str) or not stdout.strip():
        return _empty_findbugs_report()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CommandError(f"speccheck emitted invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CommandError("speccheck report must be a JSON object.")
    return payload


def _merge_speccheck_report(target: dict[str, Any], payload: dict[str, Any]) -> None:
    for key in (
        "parsed_behaviors",
        "test_case_candidates",
        "bug_candidates",
        "duplicate_warnings",
        "stale_record_warnings",
    ):
        rows = payload.get(key, [])
        if isinstance(rows, list):
            target[key].extend(rows)


def _findbugs_report_metadata(model_status: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    artifact_bytes = len(json.dumps(report, sort_keys=True).encode("utf-8"))
    return {
        "artifact_bytes": artifact_bytes,
        "level_a": dict(LEVEL_A_STATUS),
        "model_used": model_status.get("status") == "ok",
        "observability_snapshot": _observability_snapshot(),
        "scan_time": timezone.now().isoformat(),
        "scanner_version": "speccheck",
        "source_roots": [str(_repo_root())],
    }


def _observability_snapshot() -> dict[str, Any]:
    try:
        from apps.observability.services.stack_status import build_stack_status

        services = build_stack_status()
    except Exception as exc:  # pragma: no cover - depends on optional stack services.
        return {
            "healthy": False,
            "degraded_services": ["observability_snapshot_unavailable"],
            "captured_at": timezone.now().isoformat(),
            "error": str(exc)[:300],
        }
    degraded = [
        _observability_service_name(service)
        for service in services
        if _observability_service_state(service) not in {"healthy", "connected", "ok"}
    ]
    return {
        "healthy": not degraded,
        "degraded_services": degraded,
        "captured_at": timezone.now().isoformat(),
    }


def _observability_service_name(service: Mapping[str, Any]) -> str:
    return str(
        service.get("service_name")
        or service.get("name")
        or service.get("id")
        or "unknown_observability_service",
    )


def _observability_service_state(service: Mapping[str, Any]) -> str:
    return str(service.get("state") or service.get("status") or "unknown")


def _iter_findbugs_source_files() -> list[Path]:
    root = _repo_root()
    ignored = {
        ".angular",
        ".cache",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".stryker-tmp",
        ".venv",
        "backups",
        "build_tests",
        "coverage",
        "dist",
        "htmlcov",
        "media",
        "node_modules",
        "out-tsc",
        "reports",
        "static",
        "staticfiles",
        "target",
        "tests",
        "test-results",
        "venv",
        "__pycache__",
    }
    source_suffixes = {".py", ".rs", ".ts", ".js", ".go", ".cpp", ".h", ".hpp"}
    files: list[Path] = []
    for current, dirs, filenames in os.walk(root):
        dirs[:] = [
            name for name in dirs
            if name not in ignored and not name.startswith(".")
        ]
        current_path = Path(current)
        for filename in filenames:
            path = current_path / filename
            if path.suffix in source_suffixes and not _is_test_source_file(path):
                files.append(path)
    return sorted(files)


def _is_test_source_file(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("test_")
        or name.startswith("tests_")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.js")
    )


def _repo_root() -> Path:
    configured = getattr(settings, "REPO_ROOT", None) or os.environ.get("REPO_ROOT")
    return Path(configured or "/repo").resolve()


def _find_speccheck_binary() -> Path | None:
    candidates = [
        os.environ.get("SPECCHECK_BINARY"),
        "/opt/xf/compiled/active/speccheck",
        "/tmp/xf-speccheck-cargo-target/release/speccheck",  # nosec B108
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _write_smollm2_status(payload: dict[str, Any], *, root: Path | None = None) -> Path:
    status_root = _artifact_root(root) / "model"
    status_root.mkdir(parents=True, exist_ok=True)
    target = status_root / "latest.json"
    target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return target


def _write_smollm2_output(
    payload: dict[str, Any],
    *,
    root: Path | None = None,
    resource_comfort: dict[str, Any] | None = None,
    reason: str = "runner_completed",
) -> Path:
    output_root = _artifact_root(root) / "model"
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "latest-output.json"
    target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    _write_smollm2_status(
        {
            "captured_at": payload["captured_at"],
            "model": SMOLLM2_MODEL_NAME,
            "status": "ok" if payload["returncode"] == 0 else "failed",
            "reason": reason,
            "output_artifact": str(target),
            "resource_comfort": resource_comfort or {},
        },
        root=root,
    )
    return target


def _smollm2_runner_command(runner: Path, model: Path, prompt: str) -> list[str]:
    return [
        str(runner),
        "-m",
        str(model),
        "-p",
        prompt,
        "-n",
        _setting_value("FINDBUGS_SMOLLM2_PREDICT_TOKENS") or "32",
        "--temp",
        "0",
        "-c",
        _setting_value("FINDBUGS_SMOLLM2_CONTEXT_TOKENS") or "512",
        "-b",
        _setting_value("FINDBUGS_SMOLLM2_BATCH_TOKENS") or "64",
        "-ub",
        _setting_value("FINDBUGS_SMOLLM2_UBATCH_TOKENS") or "64",
        "--threads",
        _setting_value("FINDBUGS_SMOLLM2_THREADS") or "2",
        "--single-turn",
        "--simple-io",
    ]


def _smollm2_runner_failure(
    reason: str,
    detail: str,
    *,
    returncode: int,
    stdout: str,
    stderr: str,
    root: Path | None,
    resource_comfort: dict[str, Any],
) -> dict[str, Any]:
    issue = file_findbugs_health_issue(
        reason="model runner timed out" if reason == "runner_timeout" else "model runner failed",
        detail=detail,
        severity=AutoIssue.SEVERITY_HIGH,
    )
    output_payload = _smollm2_output_payload(returncode, stdout, stderr)
    artifact = _write_smollm2_output(
        output_payload,
        root=root,
        resource_comfort=resource_comfort,
        reason=reason,
    )
    status_payload = _smollm2_status_payload(
        "failed",
        reason,
        issue.id,
        resource_comfort=resource_comfort,
    )
    status_payload["output_artifact"] = str(artifact)
    _write_smollm2_status(status_payload, root=root)
    return {
        "status": "failed",
        "reason": reason,
        "artifact": str(artifact),
        "autoissue": issue.id,
        "resource_comfort": resource_comfort,
    }


def _subprocess_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _smollm2_output_payload(
    returncode: int,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    return {
        "captured_at": timezone.now().isoformat(),
        "model": SMOLLM2_MODEL_NAME,
        "returncode": returncode,
        "raw_output": stdout[:SMOLLM2_OUTPUT_LIMIT],
        "stderr": stderr[:SMOLLM2_OUTPUT_LIMIT],
    }


def _smollm2_status_payload(
    status: str,
    reason: str,
    autoissue_id: int | None,
    *,
    resource_comfort: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "captured_at": timezone.now().isoformat(),
        "model": SMOLLM2_MODEL_NAME,
        "status": status,
        "reason": reason,
        "resource_comfort": resource_comfort or {},
    }
    if autoissue_id is not None:
        payload["autoissue"] = autoissue_id
    return payload


def _findbugs_model_resource_comfort(*, embedding_busy: bool) -> dict[str, Any]:
    backend_up = _victoriametrics_instant_query('up{job="backend"}')
    queue_depth = _victoriametrics_instant_query('xf_queue_depth{queue="embeddings"}')
    if backend_up is None and queue_depth is None:
        issue = file_findbugs_health_issue(
            reason="model resource telemetry unavailable",
            detail=(
                "FindBugs kept SmolLM2 running, but VictoriaMetrics did not return "
                "resource comfort signals. Tune the observability query path so "
                "FindBugs and embeddings can be watched together."
            ),
            severity=AutoIssue.SEVERITY_MEDIUM,
        )
        return {
            "comfortable": False,
            "embedding_busy": embedding_busy,
            "reason": "victoriametrics_unavailable",
            "autoissue": issue.id,
        }
    if embedding_busy and (queue_depth or 0) > FINDBUGS_EMBEDDING_QUEUE_COMFORT_LIMIT:
        issue = file_findbugs_health_issue(
            reason="model resource tuning needed",
            detail=(
                "FindBugs kept SmolLM2 running while embeddings were busy, but "
                "VictoriaMetrics showed embedding queue pressure. Tune scheduling, "
                "RAM, or worker limits until both workloads fit comfortably."
            ),
            severity=AutoIssue.SEVERITY_MEDIUM,
        )
        return {
            "comfortable": False,
            "embedding_busy": embedding_busy,
            "reason": "embedding_queue_pressure",
            "queue_depth": queue_depth,
            "autoissue": issue.id,
        }
    return {
        "comfortable": True,
        "embedding_busy": embedding_busy,
        "reason": "comfortable",
        "queue_depth": queue_depth,
    }


def _victoriametrics_instant_query(query: str) -> float | None:
    params = urllib.parse.urlencode({"query": query})
    url = f"{VICTORIAMETRICS_URL.rstrip('/')}/api/v1/query?{params}"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.info("VictoriaMetrics query failed for FindBugs comfort check: %s", exc)
        return None
    result = payload.get("data", {}).get("result", [])
    if not result:
        return None
    value = result[0].get("value", [])
    if len(value) < 2:
        return None
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None


def _embeddings_are_busy() -> bool:
    try:
        from config.celery import app as celery_app

        inspector = celery_app.control.inspect(timeout=0.5)
        task_groups = [
            inspector.active() or {},
            inspector.reserved() or {},
            inspector.scheduled() or {},
        ]
    except Exception as exc:  # pragma: no cover - broker-dependent safety path
        logger.info("FindBugs could not inspect embedding queue state: %s", exc)
        return False
    return any(
        _task_mentions_embeddings(task)
        for group in task_groups
        for tasks in group.values()
        for task in tasks
    )


def _task_mentions_embeddings(task: dict[str, Any]) -> bool:
    text = json.dumps(task, sort_keys=True).lower()
    return "embedding" in text or '"queue": "embeddings"' in text


def _configured_smollm2_runner(path: Path | None) -> Path | None:
    candidate = path or _path_from_setting("FINDBUGS_SMOLLM2_RUNNER")
    if candidate is None or not candidate.is_file() or not os.access(candidate, os.X_OK):
        return None
    return candidate


def _configured_smollm2_model(path: Path | None) -> Path | None:
    candidate = path or _path_from_setting("FINDBUGS_SMOLLM2_MODEL")
    return candidate if candidate is not None and candidate.is_file() else None


def _configured_smollm2_server(server_url: str | None) -> str:
    if server_url is not None:
        return server_url
    if "FINDBUGS_SMOLLM2_SERVER_URL" in os.environ:
        return str(os.environ.get("FINDBUGS_SMOLLM2_SERVER_URL") or "")
    configured = _setting_value("FINDBUGS_SMOLLM2_SERVER_URL")
    if configured:
        return configured
    if _setting_value("FINDBUGS_SMOLLM2_DISABLE_DEFAULT_SERVER").lower() in {"1", "true", "yes"}:
        return ""
    return DEFAULT_SMOLLM2_SERVER_URL


def _path_from_setting(name: str) -> Path | None:
    value = _setting_value(name)
    return Path(value) if value else None


def _setting_value(name: str) -> str:
    if name in os.environ:
        return str(os.environ.get(name) or "")
    return str(getattr(settings, name, "") or "")
