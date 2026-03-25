from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("suggestions", "0007_suggestion_learned_anchor_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="suggestion",
            name="score_rare_term_propagation",
            field=models.FloatField(
                default=0.5,
                help_text="FR-010 rare-term propagation score for this destination/host sentence pair. 0.5 means neutral.",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="rare_term_diagnostics",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Explainable FR-010 rare-term propagation diagnostics for review and debugging.",
            ),
        ),
    ]
