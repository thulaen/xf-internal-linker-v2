"""Migration: add batch_label + 'proposed' status to Suggestion.

Both fields back the monthly Top-50 picker:
- `batch_label` (YYYY-MM) lets the picker dedup across months and lets the
  Monthly Reports page filter the DB rows that backed each markdown file.
- The new `'proposed'` status differentiates AI-picked suggestions awaiting
  human review from the broader `'pending'` queue (which contains everything
  the pipeline emits, regardless of whether the AI has highlighted it).

Hand-rolled (not auto-generated) so the index name is explicit and the
choices change is documented inline.

SQLite caveat: the dashboard suggestion-counts view created by
`core/0018_dashboard_suggestion_counts_mv.py` references `suggestions_
suggestion`. AddField on SQLite triggers `_remake_table` which renames
the underlying table mid-migration, breaking the view's reference. We
work around this by dropping the view before AddField and recreating
it after. On PostgreSQL the view is a real MATERIALIZED VIEW and is
unaffected by AlterField (no `_remake_table`), but we run the same
drop/recreate dance for parity (DROP MATERIALIZED VIEW IF EXISTS is
idempotent).
"""

from django.db import migrations, models


SQL_DROP_SQLITE = "DROP VIEW IF EXISTS dashboard_suggestion_counts_mv;"
SQL_DROP_PG_VIEW = "DROP MATERIALIZED VIEW IF EXISTS dashboard_suggestion_counts_mv;"
SQL_DROP_PG_INDEX = "DROP INDEX IF EXISTS dashboard_suggestion_counts_mv_status_idx;"

SQL_CREATE_SQLITE = (
    "CREATE VIEW IF NOT EXISTS dashboard_suggestion_counts_mv AS "
    "SELECT status, COUNT(*) AS count FROM suggestions_suggestion GROUP BY status;"
)
SQL_CREATE_PG_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS dashboard_suggestion_counts_mv AS
SELECT
    status,
    COUNT(*) AS count
FROM suggestions_suggestion
GROUP BY status
WITH DATA;
"""
SQL_CREATE_PG_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS dashboard_suggestion_counts_mv_status_idx
    ON dashboard_suggestion_counts_mv (status);
"""


def drop_dashboard_view(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        schema_editor.execute(SQL_DROP_SQLITE)
    else:
        schema_editor.execute(SQL_DROP_PG_INDEX)
        schema_editor.execute(SQL_DROP_PG_VIEW)


def recreate_dashboard_view(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        schema_editor.execute(SQL_CREATE_SQLITE)
    else:
        schema_editor.execute(SQL_CREATE_PG_VIEW)
        schema_editor.execute(SQL_CREATE_PG_INDEX)


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0064_seed_w_embedding_age"),
        ("core", "0018_dashboard_suggestion_counts_mv"),
    ]

    operations = [
        migrations.RunPython(drop_dashboard_view, recreate_dashboard_view),
        migrations.AddField(
            model_name="suggestion",
            name="batch_label",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "Optional batch tag stamped by the monthly Top-50 picker "
                    "(format YYYY-MM). Used for per-month dedup and to filter "
                    "the Monthly Reports page."
                ),
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="suggestion",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Review"),
                    ("proposed", "Proposed (AI-picked, awaiting human review)"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("applied", "Applied"),
                    ("verified", "Verified"),
                    ("stale", "Stale"),
                    ("superseded", "Superseded"),
                ],
                db_index=True,
                default="pending",
                help_text="Current review/lifecycle status of this suggestion.",
                max_length=20,
            ),
        ),
        migrations.RunPython(recreate_dashboard_view, drop_dashboard_view),
    ]
