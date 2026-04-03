from django.db import migrations

def apply_autovacuum(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("ALTER TABLE content_contentitem SET (autovacuum_vacuum_scale_factor = 0.05, autovacuum_vacuum_threshold = 50);")
    schema_editor.execute("ALTER TABLE content_sentence SET (autovacuum_vacuum_scale_factor = 0.01, autovacuum_vacuum_threshold = 100);")

def reverse_autovacuum(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("ALTER TABLE content_contentitem RESET (autovacuum_vacuum_scale_factor, autovacuum_vacuum_threshold);")
    schema_editor.execute("ALTER TABLE content_sentence RESET (autovacuum_vacuum_scale_factor, autovacuum_vacuum_threshold);")

class Migration(migrations.Migration):
    dependencies = [
        ('content', '0011_hnsw_indexes'),
    ]
    operations = [
        migrations.RunPython(apply_autovacuum, reverse_autovacuum),
    ]
