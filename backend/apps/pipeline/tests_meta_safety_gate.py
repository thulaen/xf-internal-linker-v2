"""FR-018b — meta-algorithm safety gate tests.

Pin the three decision paths of ``_meta_safety_gate`` (in
``apps.pipeline.tasks``):

1. ``"promote"`` — clean history, gate passes.
2. ``"reject"`` — a meta-challenger was rolled back in the last 30 days.
3. ``"escalate"`` — the last 3 meta-challengers all ended in failure
   (rolled_back or rejected), so the gate fires an OperatorAlert.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.pipeline.tasks import _meta_safety_gate
from apps.suggestions.models import RankingChallenger


def _make_challenger(
    *,
    run_id: str,
    status: str = "pending",
    kind: str = "meta_algorithm",
    created_offset_days: int = 0,
) -> RankingChallenger:
    """Helper: create one RankingChallenger row with a backdated created_at."""
    challenger = RankingChallenger.objects.create(
        run_id=run_id,
        kind=kind,
        status=status,
        candidate_weights={"pipeline.rrf_k": "60.0"},
        baseline_weights={"pipeline.rrf_k": "60.0"},
    )
    if created_offset_days:
        # auto_now_add=True overrides our value; use update() to backdate.
        new_created = timezone.now() - timedelta(days=created_offset_days)
        RankingChallenger.objects.filter(pk=challenger.pk).update(
            created_at=new_created,
            updated_at=new_created,
        )
        challenger.refresh_from_db()
    return challenger


class MetaSafetyGateTests(TestCase):
    def test_clean_history_promotes(self) -> None:
        """No prior meta-challengers → gate returns ``"promote"``."""
        c = _make_challenger(run_id="meta-0001")
        decision, reason = _meta_safety_gate(c)
        self.assertEqual(decision, "promote")
        self.assertEqual(reason, "")

    def test_recent_rollback_rejects(self) -> None:
        """A rolled_back meta-challenger in the last 30 days → reject."""
        # Prior rollback 5 days ago — within the 30-day window.
        _make_challenger(
            run_id="meta-prior",
            status="rolled_back",
            created_offset_days=5,
        )
        new = _make_challenger(run_id="meta-new")
        decision, reason = _meta_safety_gate(new)
        self.assertEqual(decision, "reject")
        self.assertIn("rollback", reason.lower())

    def test_old_rollback_does_not_block(self) -> None:
        """A rolled_back challenger 60 days ago → out of window → promote."""
        _make_challenger(
            run_id="meta-very-old",
            status="rolled_back",
            created_offset_days=60,
        )
        # The query filters on updated_at, which we backdated too.
        new = _make_challenger(run_id="meta-new-2")
        decision, _reason = _meta_safety_gate(new)
        self.assertEqual(decision, "promote")

    def test_three_consecutive_failures_escalate(self) -> None:
        """Last 3 meta-challengers all failed → escalate."""
        # Three failed challengers in different states, spaced out so
        # none falls inside the 30-day rollback window. Mix rejected
        # and rolled_back to exercise both branches of the failure set.
        _make_challenger(
            run_id="meta-old-1",
            status="rejected",
            created_offset_days=120,
        )
        _make_challenger(
            run_id="meta-old-2",
            status="rejected",
            created_offset_days=90,
        )
        _make_challenger(
            run_id="meta-old-3",
            status="rejected",
            created_offset_days=60,
        )
        new = _make_challenger(run_id="meta-new-3")
        decision, reason = _meta_safety_gate(new)
        self.assertEqual(decision, "escalate")
        self.assertIn("consistently", reason.lower())

    def test_two_consecutive_failures_still_promote(self) -> None:
        """Only 2 failures in history → not enough for escalation."""
        _make_challenger(
            run_id="meta-old-1",
            status="rejected",
            created_offset_days=120,
        )
        _make_challenger(
            run_id="meta-old-2",
            status="rejected",
            created_offset_days=90,
        )
        new = _make_challenger(run_id="meta-new-4")
        decision, _reason = _meta_safety_gate(new)
        self.assertEqual(decision, "promote")

    def test_promoted_breaks_consecutive_failure_streak(self) -> None:
        """A promoted challenger between failures resets the streak."""
        _make_challenger(
            run_id="meta-old-1",
            status="rejected",
            created_offset_days=120,
        )
        _make_challenger(
            run_id="meta-old-2",
            status="promoted",
            created_offset_days=90,
        )
        _make_challenger(
            run_id="meta-old-3",
            status="rejected",
            created_offset_days=60,
        )
        new = _make_challenger(run_id="meta-new-5")
        decision, _reason = _meta_safety_gate(new)
        # Top-3 are: meta-old-3 (rejected), meta-old-2 (promoted),
        # meta-old-1 (rejected). promoted breaks the streak → 2 failures
        # not 3 → promote.
        self.assertEqual(decision, "promote")

    def test_weight_kind_challengers_ignored(self) -> None:
        """FR-018 weight challengers don't count against meta-tuner failures."""
        # Three weight challengers all rolled back — irrelevant to the
        # meta-tuner gate which filters on kind="meta_algorithm".
        for i in range(3):
            _make_challenger(
                run_id=f"weights-{i}",
                kind="weights",
                status="rolled_back",
                created_offset_days=60 + i,
            )
        new = _make_challenger(run_id="meta-new-6")
        decision, _reason = _meta_safety_gate(new)
        self.assertEqual(decision, "promote")

    def test_self_excluded_from_history(self) -> None:
        """The challenger being evaluated isn't counted against itself."""
        # Set the challenger's own status to rolled_back to confirm it's
        # excluded by the .exclude(pk=challenger.pk) filter.
        c = RankingChallenger.objects.create(
            run_id="meta-self",
            kind="meta_algorithm",
            status="rolled_back",
            candidate_weights={"pipeline.rrf_k": "60.0"},
            baseline_weights={"pipeline.rrf_k": "60.0"},
        )
        decision, _reason = _meta_safety_gate(c)
        # Despite c.status="rolled_back", c.pk is excluded → no recent
        # rollback found → promote.
        self.assertEqual(decision, "promote")


class MetaEscalationAlertTests(TestCase):
    def test_escalation_emits_operator_alert(self) -> None:
        """When the gate returns ``"escalate"``, evaluate_meta_challenger
        calls ``emit_operator_alert``."""
        # Set up: 3 prior failures so the gate escalates.
        _make_challenger(
            run_id="meta-old-1",
            status="rejected",
            created_offset_days=120,
        )
        _make_challenger(
            run_id="meta-old-2",
            status="rejected",
            created_offset_days=90,
        )
        _make_challenger(
            run_id="meta-old-3",
            status="rejected",
            created_offset_days=60,
        )
        # New challenger to evaluate.
        target = RankingChallenger.objects.create(
            run_id="meta-target",
            kind="meta_algorithm",
            status="pending",
            candidate_weights={"pipeline.rrf_k": "60.0"},
            baseline_weights={"pipeline.rrf_k": "60.0"},
        )

        with patch(
            "apps.notifications.services.emit_operator_alert"
        ) as mock_emit:
            from apps.pipeline.tasks import evaluate_meta_challenger

            # Call the underlying function bypassing Celery's binding.
            result = evaluate_meta_challenger.run(run_id="meta-target")

        target.refresh_from_db()
        self.assertEqual(target.status, "rejected")
        self.assertEqual(result.get("status"), "gate_escalate")
        mock_emit.assert_called_once()
