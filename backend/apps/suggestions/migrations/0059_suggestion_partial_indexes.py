"""Phase 2.24 — partial indexes on Suggestion for the review-queue hot path.

The review queue runs::

    Suggestion.objects.filter(status="pending").order_by("-score_final")

every time the operator opens ``/review`` and on every WebSocket
notification refresh. ``status="pending"`` typically covers 5-15 % of all
``Suggestion`` rows (the rest are approved, rejected, applied, or
superseded). A *partial* index ``WHERE status = 'pending'`` is dramatically
smaller than the full ``(status, score_final)`` compound index and much
faster to walk — Postgres scans only the pending subset rather than
seeking past the approved/rejected blocks.

Citation: PostgreSQL docs §11.8 "Partial Indexes".

Two partial indexes shipped:

  * ``sug_pending_score_idx`` — ordered by score_final DESC, used by the
    review queue's primary listing.
  * ``sug_pending_updated_idx`` — ordered by updated_at DESC, used by the
    "recently changed pending" lane and by some retention scans.

The existing compound ``(status, score_final)`` index stays in place for
queries that filter on other statuses (approved-history page, audit
queries). Postgres planner picks whichever index is smaller for the
specific query.

Idempotent: ``IF NOT EXISTS`` guards make this safe to re-run.
"""

from django.db import migrations


SQL_CREATE_PENDING_SCORE_IDX = """
CREATE INDEX IF NOT EXISTS sug_pending_score_idx
    ON suggestions_suggestion (score_final DESC)
    WHERE status = 'pending';
"""

SQL_DROP_PENDING_SCORE_IDX = "DROP INDEX IF EXISTS sug_pending_score_idx;"

SQL_CREATE_PENDING_UPDATED_IDX = """
CREATE INDEX IF NOT EXISTS sug_pending_updated_idx
    ON suggestions_suggestion (updated_at DESC)
    WHERE status = 'pending';
"""

SQL_DROP_PENDING_UPDATED_IDX = "DROP INDEX IF EXISTS sug_pending_updated_idx;"


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0058_passage_relevance_full_defaults"),
    ]
    operations = [
        migrations.RunSQL(
            sql=SQL_CREATE_PENDING_SCORE_IDX,
            reverse_sql=SQL_DROP_PENDING_SCORE_IDX,
        ),
        migrations.RunSQL(
            sql=SQL_CREATE_PENDING_UPDATED_IDX,
            reverse_sql=SQL_DROP_PENDING_UPDATED_IDX,
        ),
    ]
