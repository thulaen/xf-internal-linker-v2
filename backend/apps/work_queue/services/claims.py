from __future__ import annotations

from django.db import transaction

from apps.work_queue.models import AgentWorkClaim
from apps.work_queue.services.gui_projection import rehearse_item
from apps.work_queue.services.items import affected_files_for, load_item, parse_item_key


@transaction.atomic
def claim_item(*, item_key: str, agent: str) -> dict:
    ref = parse_item_key(item_key)
    item = load_item(ref)
    files = affected_files_for(item)
    conflict = _find_file_conflict(files, agent)
    claim = AgentWorkClaim.objects.create(
        item_kind=ref.kind,
        item_id=ref.id,
        item_key=ref.key,
        agent=agent[:80],
        status=AgentWorkClaim.STATUS_CONFLICTED if conflict else AgentWorkClaim.STATUS_CLAIMED,
        affected_files=files,
        conflict_reason=conflict,
        next_action=rehearse_item(item_key)["next_action"],
    )
    return claim_payload(claim)


def release_item(*, item_key: str, agent: str) -> dict:
    claim = AgentWorkClaim.objects.filter(
        item_key=item_key,
        agent=agent[:80],
        status__in=[AgentWorkClaim.STATUS_CLAIMED, AgentWorkClaim.STATUS_CONFLICTED],
    ).order_by("-claimed_at").first()
    if claim is None:
        return {"released": False, "detail": "No active claim found for this agent."}
    claim.release()
    return {"released": True, "claim": claim_payload(claim)}


def claim_payload(claim: AgentWorkClaim) -> dict:
    return {
        "id": claim.id,
        "item_key": claim.item_key,
        "agent": claim.agent,
        "status": claim.status,
        "affected_files": claim.affected_files,
        "conflict_reason": claim.conflict_reason,
        "next_action": claim.next_action,
        "claimed_at": claim.claimed_at.isoformat(),
    }


def _find_file_conflict(files: list[str], agent: str) -> str:
    if not files:
        return ""
    wanted = set(files)
    active_claims = AgentWorkClaim.objects.filter(
        status=AgentWorkClaim.STATUS_CLAIMED,
    ).exclude(agent=agent[:80])[:50]
    for active in active_claims:
        if wanted.intersection(set(active.affected_files or [])):
            return f"{active.agent} already claimed overlapping files."
    return ""
