import pytest
from apps.work_queue.models import AgentRepairAttempt
from apps.work_queue.services.agent_attempts import record_repair_attempt, attempt_quality_summary

@pytest.mark.django_db
def test_record_repair_attempt_success():
    payload = record_repair_attempt(
        item_key="autoissue-100",
        agent="gemini",
        attempt_fingerprint="fingerprint1",
        result=AgentRepairAttempt.RESULT_PASSED,
    )
    assert payload["result"] == AgentRepairAttempt.RESULT_PASSED
    assert payload["blocked_by_loop_cap"] is False
    assert payload["prior_failed_repeats"] == 0

@pytest.mark.django_db
def test_record_repair_attempt_blocked():
    # Setup 3 prior failures
    for _ in range(3):
        AgentRepairAttempt.objects.create(
            item_kind="autoissue",
            item_id=100,
            item_key="autoissue-100",
            agent="gemini",
            attempt_fingerprint="fingerprint1",
            result=AgentRepairAttempt.RESULT_FAILED,
        )
    
    # 4th failure should be blocked
    payload = record_repair_attempt(
        item_key="autoissue-100",
        agent="gemini",
        attempt_fingerprint="fingerprint1",
        result=AgentRepairAttempt.RESULT_FAILED,
    )
    assert payload["result"] == AgentRepairAttempt.RESULT_BLOCKED
    assert payload["blocked_by_loop_cap"] is True
    assert payload["prior_failed_repeats"] == 3

@pytest.mark.django_db
def test_attempt_quality_summary():
    AgentRepairAttempt.objects.create(
        item_kind="autoissue",
        item_id=100,
        item_key="autoissue-100",
        agent="gemini",
        attempt_fingerprint="fingerprint1",
        result=AgentRepairAttempt.RESULT_FAILED,
    )
    AgentRepairAttempt.objects.create(
        item_kind="autoissue",
        item_id=100,
        item_key="autoissue-100",
        agent="gemini",
        attempt_fingerprint="fingerprint2",
        result=AgentRepairAttempt.RESULT_BLOCKED,
    )
    
    summary = attempt_quality_summary("autoissue-100")
    assert summary["attempt_count"] == 2
    assert summary["failed_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["last_attempt_at"] is not None


