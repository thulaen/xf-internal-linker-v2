from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("suggestions", "0008_suggestion_rare_term_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="suggestion",
            name="field_aware_diagnostics",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Explainable FR-011 field-aware relevance diagnostics for review and debugging.",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="score_field_aware_relevance",
            field=models.FloatField(
                default=0.5,
                help_text="FR-011 field-aware relevance score for this destination/host sentence pair. 0.5 means neutral.",
            ),
        ),
    ]
