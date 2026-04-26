"""Decommission C# labels: backfill cs_auto_tune source values and refresh
RankingChallenger / WeightAdjustmentHistory help_text strings.

Migration 0028 (2026-04-12) removed ``cs_auto_tune`` from
``WeightAdjustmentHistory.SOURCE_CHOICES`` but left existing rows untouched.
This migration brings stored data back in line with the choices list and
updates the user-facing help_text for the FR-018 RankingChallenger fields
to reflect that the auto-tuner is now Python (not the decommissioned C#
HTTP worker).
"""

from django.db import migrations, models


def backfill_cs_auto_tune_source(apps, schema_editor):
    WeightAdjustmentHistory = apps.get_model("suggestions", "WeightAdjustmentHistory")
    WeightAdjustmentHistory.objects.filter(source="cs_auto_tune").update(
        source="auto_tune"
    )


def reverse_noop(apps, schema_editor):
    # Forward-only: SOURCE_CHOICES no longer accepts cs_auto_tune (removed in
    # migration 0028), so reversing the backfill would leave rows in an
    # invalid state. The reverse path is intentionally a no-op.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0047_seed_anti_garbage_anchor_defaults"),
    ]

    operations = [
        migrations.AlterField(
            model_name="weightadjustmenthistory",
            name="r_run_id",
            field=models.CharField(
                blank=True,
                help_text="Reference to the auto-tune run (populated by FR-018 when active).",
                max_length=200,
            ),
        ),
        migrations.AlterField(
            model_name="rankingchallenger",
            name="run_id",
            field=models.CharField(
                help_text="Opaque identifier from the Python auto-tune run (UUID4).",
                max_length=200,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="rankingchallenger",
            name="baseline_weights",
            field=models.JSONField(
                default=dict,
                help_text="Snapshot of the four active weights at the moment the auto-tuner submitted this challenger.",
            ),
        ),
        migrations.AlterField(
            model_name="rankingchallenger",
            name="predicted_quality_score",
            field=models.FloatField(
                blank=True,
                help_text="Predicted link-quality score from the Python L-BFGS-B optimizer for the candidate weights (1 / (1 + BCE-loss)).",
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_cs_auto_tune_source,
            reverse_code=reverse_noop,
        ),
    ]
