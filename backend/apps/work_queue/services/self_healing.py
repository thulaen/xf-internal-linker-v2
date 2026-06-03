from __future__ import annotations

from django.utils import timezone

from apps.work_queue.models import SelfHealingDecision


AGENT_AUTHOR_HINTS = ("codex", "claude", "gemini", "antigravity", "agent")


def latest_self_healing_status() -> dict:
    decision = SelfHealingDecision.objects.first()
    if decision is None:
        decision = SelfHealingDecision.objects.create(
            status=SelfHealingDecision.STATUS_WATCHING,
            reason="No rollback decision has been needed yet.",
        )
    return decision_payload(decision)


def record_self_healing_decision(
    *,
    latest_commit_sha: str,
    latest_commit_author: str,
    backend_health: str,
    frontend_health: str,
    dirty_worktree: bool,
) -> SelfHealingDecision:
    agent_authored = _is_agent_author(latest_commit_author)
    status, reason = _decide(agent_authored, backend_health, frontend_health, dirty_worktree)
    return SelfHealingDecision.objects.create(
        latest_commit_sha=latest_commit_sha,
        latest_commit_author=latest_commit_author,
        agent_authored=agent_authored,
        backend_health=backend_health,
        frontend_health=frontend_health,
        dirty_worktree=dirty_worktree,
        status=status,
        reason=reason,
    )


def approve_decision(decision_id: int) -> dict:
    decision = SelfHealingDecision.objects.get(pk=decision_id)
    decision.approved_at = timezone.now()
    decision.save(update_fields=["approved_at"])
    return decision_payload(decision)


def decision_payload(decision: SelfHealingDecision) -> dict:
    return {
        "id": decision.id,
        "latest_commit_sha": decision.latest_commit_sha,
        "latest_commit_author": decision.latest_commit_author,
        "agent_authored": decision.agent_authored,
        "backend_health": decision.backend_health,
        "frontend_health": decision.frontend_health,
        "dirty_worktree": decision.dirty_worktree,
        "status": decision.status,
        "reason": decision.reason,
        "allowed_action": _allowed_action(decision),
        "created_at": decision.created_at.isoformat(),
        "approved_at": decision.approved_at.isoformat() if decision.approved_at else None,
    }


def _is_agent_author(author: str) -> bool:
    lowered = (author or "").lower()
    return any(hint in lowered for hint in AGENT_AUTHOR_HINTS)


def _decide(agent_authored: bool, backend: str, frontend: str, dirty: bool) -> tuple[str, str]:
    broken = backend == "failed" or frontend == "failed"
    if not broken:
        return SelfHealingDecision.STATUS_WATCHING, "Backend and frontend checks are not failing."
    if dirty:
        return SelfHealingDecision.STATUS_MANUAL_REVIEW, "The worktree is dirty, so automatic revert is unsafe."
    if not agent_authored:
        return SelfHealingDecision.STATUS_BLOCKED, "The latest commit is not agent-authored."
    return SelfHealingDecision.STATUS_REVERT_RECOMMENDED, "Only the latest agent-authored commit is eligible."


def _allowed_action(decision: SelfHealingDecision) -> str:
    if decision.status == SelfHealingDecision.STATUS_REVERT_RECOMMENDED:
        return "manual_approve_revert"
    return "watch"

