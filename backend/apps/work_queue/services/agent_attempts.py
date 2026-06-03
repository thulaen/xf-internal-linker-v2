from __future__ import annotations

from django.db.models import Count

from apps.work_queue.models import AgentRepairAttempt
from apps.work_queue.services.items import parse_item_key

MAX_FAILED_ATTEMPTS = 3


def record_repair_attempt(
    *,
    item_key: str,
    agent: str,
    attempt_fingerprint: str,
    result: str,
    command: str = "",
    summary: str = "",
    blocker: str = "",
    next_action: str = "",
) -> dict:
    ref = parse_item_key(item_key)
    failure_count = _same_failed_attempts(item_key, agent, attempt_fingerprint)
    blocked = result == AgentRepairAttempt.RESULT_FAILED and failure_count >= MAX_FAILED_ATTEMPTS
    final_result = AgentRepairAttempt.RESULT_BLOCKED if blocked else result
    attempt = AgentRepairAttempt.objects.create(
        item_kind=ref.kind,
        item_id=ref.id,
        item_key=ref.key,
        agent=agent[:80],
        attempt_fingerprint=attempt_fingerprint[:64],
        result=final_result,
        command=command,
        summary=summary,
        blocker=blocker,
        next_action=next_action,
    )
    return _attempt_payload(attempt, blocked=blocked, prior_failures=failure_count)


def attempt_quality_summary(item_key: str) -> dict:
    rows = AgentRepairAttempt.objects.filter(item_key=item_key)
    counts = dict(rows.values_list("result").annotate(c=Count("id")))
    return {
        "attempt_count": rows.count(),
        "failed_count": int(counts.get(AgentRepairAttempt.RESULT_FAILED, 0)),
        "blocked_count": int(counts.get(AgentRepairAttempt.RESULT_BLOCKED, 0)),
        "last_attempt_at": rows.order_by("-created_at").values_list("created_at", flat=True).first(),
    }


def _same_failed_attempts(item_key: str, agent: str, fingerprint: str) -> int:
    return AgentRepairAttempt.objects.filter(
        item_key=item_key,
        agent=agent[:80],
        attempt_fingerprint=fingerprint[:64],
        result=AgentRepairAttempt.RESULT_FAILED,
    ).count()


def _attempt_payload(attempt: AgentRepairAttempt, *, blocked: bool, prior_failures: int) -> dict:
    return {
        "id": attempt.id,
        "item_key": attempt.item_key,
        "agent": attempt.agent,
        "result": attempt.result,
        "blocked_by_loop_cap": blocked,
        "prior_failed_repeats": prior_failures,
        "next_action": attempt.next_action or "Write a final report instead of repeating the same fix.",
    }

