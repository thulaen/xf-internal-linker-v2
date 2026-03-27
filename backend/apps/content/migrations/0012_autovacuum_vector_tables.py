from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('content', '0011_hnsw_indexes'),
    ]
    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE content_contentitem SET (autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_threshold = 50);",
            reverse_sql="ALTER TABLE content_contentitem RESET (autovacuum_vacuum_scale_factor, autovacuum_vacuum_threshold);",
        ),
        migrations.RunSQL(
            sql="ALTER TABLE content_sentence SET (autovacuum_vacuum_scale_factor = 0.01, autovacuum_vacuum_threshold = 100);",
            reverse_sql="ALTER TABLE content_sentence RESET (autovacuum_vacuum_scale_factor, autovacuum_vacuum_threshold);",
        ),
    ]
