"""
Migration 0015 — add WeightPreset and WeightAdjustmentHistory models.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("suggestions", "0014_fr015_slate_diversity"),
    ]

    operations = [
        migrations.CreateModel(
            name="WeightPreset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when this record was created.")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when this record was last modified.")),
                ("name", models.CharField(help_text="Friendly name for this preset, e.g. 'Recommended' or 'Authority-heavy'.", max_length=200, unique=True)),
                ("is_system", models.BooleanField(db_index=True, default=False, help_text="System presets are read-only and cannot be modified or deleted via the API.")),
                ("weights", models.JSONField(default=dict, help_text="Flat key/value map of AppSetting keys → values for all settings in categories ml, link_freshness, and anchor.")),
            ],
            options={
                "verbose_name": "Weight Preset",
                "verbose_name_plural": "Weight Presets",
                "ordering": ["-is_system", "name"],
            },
        ),
        migrations.CreateModel(
            name="WeightAdjustmentHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(
                    choices=[("r_auto", "Monthly R auto-tune"), ("manual", "Manual save"), ("preset_applied", "Preset applied")],
                    db_index=True,
                    max_length=20,
                    help_text="What triggered this weight change.",
                )),
                ("preset", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="adjustment_history",
                    to="suggestions.weightpreset",
                    help_text="The preset that was applied (only set when source='preset_applied').",
                )),
                ("previous_weights", models.JSONField(default=dict, help_text="Snapshot of all in-scope weights before the change.")),
                ("new_weights", models.JSONField(default=dict, help_text="Snapshot of all in-scope weights after the change.")),
                ("delta", models.JSONField(default=dict, help_text="Only the keys that changed, with {previous, new} sub-keys.")),
                ("reason", models.CharField(max_length=500, help_text="Plain-English summary.")),
                ("r_run_id", models.CharField(blank=True, max_length=200, help_text="Reference to the R analytics run (populated by FR-018 when active).")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, help_text="When this adjustment was recorded.")),
            ],
            options={
                "verbose_name": "Weight Adjustment",
                "verbose_name_plural": "Weight Adjustment History",
                "ordering": ["-created_at"],
            },
        ),
    ]
