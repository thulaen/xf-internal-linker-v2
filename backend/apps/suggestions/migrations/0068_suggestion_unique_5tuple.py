"""Adds the 5-tuple UniqueConstraint to Suggestion table.

Closes AutoIssue #11 + RPT-004 row 4 (NO-DUPLICATES.md invariant).

The expected unique key per the boot-time audit (`ARTIFACT_RULES` in
`apps.core.services.self_test_smoke`) is
`(pipeline_run, host, destination, host_sentence_text, anchor_phrase)`.
Without enforcement, two pipeline reruns over the same corpus could
leave duplicate suggestion rows, doubling the review queue.

Safety check (run 2026-05-10): the live `suggestions_suggestion` table
has 0 rows, so the new constraint cannot fail due to existing data.
Pure schema change.

The migration uses an `UnsupportedOperationException`-safe dedup-first
phase even though no rows exist today — future deployments where the
table is non-empty when this migration runs (e.g. a re-creation from
backup) will dedup automatically rather than fail.
"""
from __future__ import annotations

from django.db import migrations, models


def _dedup_suggestions(apps, schema_editor) -> None:
    """Keep the latest suggestion per 5-tuple; delete older duplicates.

    No-op when the table is empty (the 2026-05-10 baseline). Defensive
    against future cases where this migration runs against a table that
    accumulated duplicates between sessions.
    """
    Suggestion = apps.get_model("suggestions", "Suggestion")
    from django.db.models import Count

    dup_groups = (
        Suggestion.objects.values(
            "pipeline_run",
            "host",
            "destination",
            "host_sentence_text",
            "anchor_phrase",
        )
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
    )
    deleted_total = 0
    for group in dup_groups:
        rows = list(
            Suggestion.objects.filter(
                pipeline_run=group["pipeline_run"],
                host=group["host"],
                destination=group["destination"],
                host_sentence_text=group["host_sentence_text"],
                anchor_phrase=group["anchor_phrase"],
            )
            .order_by("-updated_at", "-suggestion_id")
            .values_list("pk", flat=True)
        )
        if len(rows) <= 1:
            continue
        deleted, _ = Suggestion.objects.filter(pk__in=rows[1:]).delete()
        deleted_total += deleted
    if deleted_total:
        print(f"[suggestions.0068] dedup'd {deleted_total} duplicate Suggestion rows")  # print-allowed: data-migration progress


def _noop_reverse(apps, schema_editor) -> None:
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("suggestions", "0067_rankingchallenger_kind"),
    ]

    operations = [
        migrations.RunPython(_dedup_suggestions, _noop_reverse),
        migrations.AddConstraint(
            model_name="suggestion",
            constraint=models.UniqueConstraint(
                fields=(
                    "pipeline_run",
                    "host",
                    "destination",
                    "host_sentence_text",
                    "anchor_phrase",
                ),
                name="unique_suggestion_per_pipeline_pair",
            ),
        ),
    ]
