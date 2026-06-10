from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auto_issues', '0023_add_megalinter_source'),
    ]

    operations = [
        migrations.AlterField(
            model_name='autoissue',
            name='source',
            field=models.CharField(
                choices=[
                    ('glitchtip', 'GlitchTip'),
                    ('pyroscope', 'Pyroscope'),
                    ('tempo', 'Tempo'),
                    ('loki', 'Loki'),
                    ('faro', 'Faro'),
                    ('sonarqube', 'SonarQube'),
                    ('vmalert', 'vmalert'),
                    ('rust_defect', 'Rust defect'),
                    ('pprof', 'pprof'),
                    ('alloy', 'Alloy'),
                    ('perfetto', 'Perfetto'),
                    ('gwp_asan', 'GWP-ASan'),
                    ('prometheus', 'Prometheus'),
                    ('pg_stat', 'pg_stat'),
                    ('lighthouse', 'Lighthouse'),
                    ('test_failure', 'Test failure'),
                    ('agent', 'Agent find'),
                    ('mutation', 'Mutation testing'),
                    ('fuzz', 'Fuzz testing'),
                    ('contract', 'Contract drift'),
                    ('gh_ci', 'GH Actions CI failure'),
                    ('compiler', 'Compiler/linter warning'),
                    ('megalinter', 'MegaLinter'),
                    ('precommit_warn', 'Pre-commit warning'),
                ],
                db_index=True,
                max_length=16,
            ),
        ),
    ]
