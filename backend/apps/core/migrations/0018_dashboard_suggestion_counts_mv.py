"""Phase 2.18 — pre-aggregated materialized view for dashboard suggestion counts.

The slowest aggregate on the Dashboard view is::

    Suggestion.objects.values("status").annotate(count=Count("pk"))

It scans every row in ``suggestions_suggestion`` (which grows linearly with the
corpus + history) on every dashboard refresh. With ~100,000 suggestions the
query runs in 600-900 ms; multiply by every operator refresh and it becomes
the dashboard's dominant latency.

A Postgres ``MATERIALIZED VIEW`` precomputes the same aggregate. Refresh runs
on a 5-minute Celery beat tick (separate task at
``apps.core.tasks_dashboard.refresh_dashboard_matviews``) using
``REFRESH MATERIALIZED VIEW CONCURRENTLY`` so reads never block. The matview
is invalidated by either the periodic refresh or a manual trigger after a
bulk operation that creates/changes thousands of suggestion rows.

Citation: PostgreSQL docs §38.3 "Materialized Views".

Stale-data tolerance: ≤5 minutes. The dashboard already shows recent (≤5 min
old) pipeline-run summaries via direct queries — staleness here is bounded
by the same window, so the operator's mental model stays consistent.

Concurrent refresh requires a unique index, hence the second operation.
"""

from django.db import migrations


SQL_CREATE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS dashboard_suggestion_counts_mv AS
SELECT
    status,
    COUNT(*) AS count
FROM suggestions_suggestion
GROUP BY status
WITH DATA;
"""

SQL_DROP_MV = """
DROP MATERIALIZED VIEW IF EXISTS dashboard_suggestion_counts_mv;
"""

# Concurrent refresh requires a unique index covering every visible row.
# ``status`` is unique per matview row by definition (one row per status).
SQL_CREATE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS dashboard_suggestion_counts_mv_status_idx
    ON dashboard_suggestion_counts_mv (status);
"""

SQL_DROP_INDEX = """
DROP INDEX IF EXISTS dashboard_suggestion_counts_mv_status_idx;
"""


def create_dashboard_mv(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        # SQLite is only used in tests. The CREATE VIEW would fire fine here
        # but every later migration that does AddField on suggestions_suggestion
        # triggers SQLite's `_remake_table`, which renames the table mid-flight
        # and breaks any view that references it ("error in view ...: no such
        # table"). The view is also not useful in tests — REFRESH MATERIALIZED
        # VIEW is Postgres-only and the tests don't exercise the dashboard's
        # matview-fast-path. Skip view creation on SQLite entirely.
        return
    schema_editor.execute(SQL_CREATE_MV)
    schema_editor.execute(SQL_CREATE_INDEX)


def drop_dashboard_mv(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        # Symmetric with create_dashboard_mv: nothing to drop on SQLite because
        # nothing was created. DROP VIEW IF EXISTS is still safe to call but
        # offers no value, so we just no-op for clarity.
        return
    # Cannot reliably DROP IF EXISTS for index in standard SQL without risking
    # errors but since we used IF EXISTS in the raw SQL constants we can just
    # run them.
    schema_editor.execute(SQL_DROP_INDEX)
    schema_editor.execute(SQL_DROP_MV)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_seed_group_l_defaults"),
        ("suggestions", "0058_passage_relevance_full_defaults"),
    ]

    operations = [
        migrations.RunPython(
            code=create_dashboard_mv,
            reverse_code=drop_dashboard_mv,
        ),
    ]
