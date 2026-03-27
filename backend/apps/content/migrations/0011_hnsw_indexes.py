from django.db import migrations

class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ('content', '0010_bge_m3_embedding_dim_1024'),
    ]
    operations = [
        migrations.RunSQL(
            sql="CREATE INDEX CONCURRENTLY IF NOT EXISTS content_item_embedding_hnsw_idx ON content_contentitem USING hnsw (embedding vector_cosine_ops);",
            reverse_sql="DROP INDEX IF EXISTS content_item_embedding_hnsw_idx;",
        ),
        migrations.RunSQL(
            sql="CREATE INDEX CONCURRENTLY IF NOT EXISTS sentence_embedding_hnsw_idx ON content_sentence USING hnsw (embedding vector_cosine_ops);",
            reverse_sql="DROP INDEX IF EXISTS sentence_embedding_hnsw_idx;",
        ),
    ]
