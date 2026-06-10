import pytest
from apps.work_queue.models import AgentWorkClaim

@pytest.mark.django_db
def test_agent_work_claim_release():
    claim = AgentWorkClaim.objects.create(
        item_kind="test_kind",
        item_id=1,
        item_key="test_kind:1",
        agent="test_agent",
        status=AgentWorkClaim.STATUS_CLAIMED,
    )
    assert claim.status == AgentWorkClaim.STATUS_CLAIMED
    assert claim.released_at is None
    
    claim.release()
    
    assert claim.status == AgentWorkClaim.STATUS_RELEASED
    assert claim.released_at is not None

