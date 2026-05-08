"""Drop 4 orphan NOT NULL columns on Suggestion that have no source backing.

Background: a deleted-from-source migration
``0011_suggestion_feedback_rerank_fields`` (only ``.pyc`` survives in
``__pycache__``) added 4 NOT NULL columns to ``suggestions_suggestion``::

    feedback_bucket_key
    feedback_rerank_diagnostics
    score_feedback_rerank
    score_phrase_quality

The current ``Suggestion`` model defines none of them. Every Suggestion
INSERT failed with::

    IntegrityError: null value in column "<orphan_column>"
    of relation "suggestions_suggestion" violates not-null constraint

That broke 11 analytics tests + the persist-suggestions regression test
+ any production write to the table. The replacement work landed in
``0012_fr013_feedback_reranking`` which uses different field names
(``feedback_score``, ``feedback_diagnostics``, etc.) — these 4 are
abandoned prototype columns.

This migration drops them all. Fully backwards-compatible because no
source code reads or writes any of them.

Bug found 2026-05-05.
"""

from __future__ import annotations

from django.db import migrations


_ORPHAN_COLUMNS = (
    "feedback_bucket_key",
    "feedback_rerank_diagnostics",
    "score_feedback_rerank",
    "score_phrase_quality",
)


def _drop_orphan_columns(apps, schema_editor):
    """Drop each orphan column (+ dependent indexes) if present."""
    with schema_editor.connection.cursor() as cursor:
        try:
            columns = [
                col.name
                for col in schema_editor.connection.introspection.get_table_description(
                    cursor, "suggestions_suggestion"
                )
            ]
        except Exception:
            return  # Table might not exist yet or other introspection error

        for column in _ORPHAN_COLUMNS:
            if column not in columns:
                continue  # Already absent on fresh DBs — no-op.

            if schema_editor.connection.vendor == "sqlite":
                # SQLite doesn't support DROP COLUMN CASCADE or DROP COLUMN in older versions easily
                # but since tests start fresh, these columns shouldn't even exist.
                # If they do, we can try a basic drop.
                try:
                    cursor.execute(
                        f'ALTER TABLE suggestions_suggestion DROP COLUMN "{column}"'
                    )
                except Exception:
                    pass
            else:
                # CASCADE drops dependent indexes. Safe — orphans have no FK targets.
                cursor.execute(
                    f"ALTER TABLE suggestions_suggestion "
                    f'DROP COLUMN "{column}" CASCADE'
                )


def _noop_reverse(apps, schema_editor):
    """Reverse migration is a no-op — we don't restore orphan columns.

    If a future feature genuinely needs any of these names back, define
    the field on the model and run ``makemigrations`` — that's the
    supported path.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0059_suggestion_partial_indexes"),
    ]

    operations = [
        migrations.RunPython(_drop_orphan_columns, _noop_reverse),
    ]
