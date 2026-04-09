from django.db import migrations


def apply_hnsw_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS content_item_embedding_hnsw_idx ON content_contentitem USING hnsw (embedding vector_cosine_ops);"
    )
    schema_editor.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS sentence_embedding_hnsw_idx ON content_sentence USING hnsw (embedding vector_cosine_ops);"
    )


def reverse_hnsw_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS content_item_embedding_hnsw_idx;")
    schema_editor.execute("DROP INDEX IF EXISTS sentence_embedding_hnsw_idx;")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ("content", "0010_bge_m3_embedding_dim_1024"),
    ]
    operations = [
        migrations.RunPython(apply_hnsw_indexes, reverse_hnsw_indexes),
    ]
