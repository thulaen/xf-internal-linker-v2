from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auto_issues", "0017_findbugs_learned_lesson"),
    ]

    operations = [
        migrations.AlterField(
            model_name="autoissue",
            name="source",
            field=models.CharField(
                choices=[
                    ("glitchtip", "GlitchTip"),
                    ("pyroscope", "Pyroscope"),
                    ("tempo", "Tempo"),
                    ("loki", "Loki"),
                    ("faro", "Faro"),
                    ("sonarqube", "SonarQube"),
                    ("vmalert", "vmalert"),
                    ("rust_defect", "Rust defect"),
                    ("agent", "Agent find"),
                    ("mutation", "Mutation testing"),
                    ("fuzz", "Fuzz testing"),
                    ("contract", "Contract drift"),
                    ("gh_ci", "GH Actions CI failure"),
                    ("pprof", "pprof"),
                    ("alloy", "alloy"),
                    ("perfetto", "Perfetto"),
                    ("gwp_asan", "GWP-ASan"),
                    ("prometheus", "Prometheus"),
                    ("pg_stat", "pg_stat_statements"),
                    ("lighthouse", "Lighthouse"),
                    ("test_failure", "Test failure"),
                ],
                db_index=True,
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="autoissue",
            name="artifact_refs",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="References to evidence blobs in the Mint blob store. No body content — SHA-256 + path only.",
            ),
        ),
    ]
