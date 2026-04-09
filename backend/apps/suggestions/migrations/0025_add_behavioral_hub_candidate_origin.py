from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0024_upsert_engagement_signal_preset_keys"),
    ]

    operations = [
        migrations.AlterField(
            model_name="suggestion",
            name="candidate_origin",
            field=models.CharField(
                choices=[
                    ("embedding", "Embedding Similarity"),
                    ("graph_walk", "Pixie Graph Walk"),
                    ("both", "Both Channel Match"),
                    ("behavioral_hub", "Behavioral Hub"),
                ],
                db_index=True,
                default="embedding",
                help_text="Which candidate generation channel produced this suggestion.",
                max_length=20,
            ),
        ),
    ]
