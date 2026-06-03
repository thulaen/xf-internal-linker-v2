"""Add SonarQube as a first-class AutoIssue source."""

from django.db import migrations, models


SOURCE_CHOICES = [
    ("glitchtip", "GlitchTip"),
    ("pyroscope", "Pyroscope"),
    ("tempo", "Tempo"),
    ("loki", "Loki"),
    ("faro", "Faro"),
    ("sonarqube", "SonarQube"),
    ("agent", "Agent find"),
    ("mutation", "Mutation testing"),
    ("fuzz", "Fuzz testing"),
    ("contract", "Contract drift"),
    ("gh_ci", "GH Actions CI failure"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("auto_issues", "0013_autoissue_concept_tags"),
    ]

    operations = [
        migrations.AlterField(
            model_name="autoissue",
            name="source",
            field=models.CharField(
                choices=SOURCE_CHOICES,
                db_index=True,
                max_length=16,
            ),
        ),
    ]
