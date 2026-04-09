from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0013_fr014_clustering_scores"),
    ]

    operations = [
        migrations.AddField(
            model_name="suggestion",
            name="score_slate_diversity",
            field=models.FloatField(
                null=True,
                blank=True,
                help_text="FR-015 MMR diversity score for this suggestion's slot in the host slate. Null when diversity reranking is disabled.",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="slate_diversity_diagnostics",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Explainable FR-015 MMR slot selection details for review and debugging.",
            ),
        ),
    ]
