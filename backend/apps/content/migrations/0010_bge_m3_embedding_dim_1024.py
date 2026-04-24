from django.db import migrations, models
from pgvector.django import VectorField


def null_embeddings(apps, schema_editor):
    """Null existing embeddings so they can be regenerated at 1024 dim (BGE-M3).

    This is a one-shot migration for the 768 → 1024 dim schema change. Guarded
    against destructive re-application:

    - If ``content_supersededembedding`` already exists (migration 0020+ applied),
      the schema is past this state. Re-nulling would destroy data that downstream
      migrations rely on, so skip.
    - If there are no existing embeddings (fresh DB), silently no-op — avoids the
      scary "all embeddings have been nulled" message in CI and fresh-container boots.
    - Otherwise, null the legacy 768-dim vectors and print an honest message.

    The runtime archival hook in ``apps/pipeline/services/embeddings.py`` handles
    provider-swap and model-upgrade archival at the batch-flush level.
    """
    ContentItem = apps.get_model("content", "ContentItem")
    Sentence = apps.get_model("content", "Sentence")

    # Guard 1: if the archive table already exists, we are re-running on a
    # post-0020 schema. Preserve data.
    try:
        existing_tables = schema_editor.connection.introspection.table_names()
    except Exception:
        existing_tables = []
    if "content_supersededembedding" in existing_tables:
        print(
            "\n-- Migration 0010: content_supersededembedding table already exists — "
            "schema is past this migration state. Skipping null to preserve embeddings."
        )
        return

    # Guard 2: fresh DB with no embeddings — nothing to do.
    existing_count = ContentItem.objects.filter(embedding__isnull=False).count()
    if existing_count == 0:
        return

    ContentItem.objects.all().update(embedding=None)
    Sentence.objects.all().update(embedding=None)
    print(
        f"\n-- Migration 0010: nulled {existing_count} pre-1024-dim embeddings. "
        f"Re-run the embed pipeline to repopulate."
    )


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0009_add_content_value_score"),
    ]
    operations = [
        migrations.RunPython(null_embeddings),
        migrations.AlterField(
            model_name="contentitem",
            name="embedding",
            field=VectorField(
                blank=True,
                dimensions=1024,
                help_text="1024-dimension sentence embedding for semantic similarity search via pgvector.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="sentence",
            name="word_position",
            field=models.IntegerField(
                default=0,
                help_text="Word offset of the sentence start in the post. Sentences with word_position > HOST_SCAN_WORD_LIMIT are excluded from host scanning.",
            ),
        ),
        migrations.AlterField(
            model_name="sentence",
            name="embedding",
            field=VectorField(
                blank=True,
                dimensions=1024,
                help_text="1024-dimension sentence embedding. Used in stage-2 similarity ranking.",
                null=True,
            ),
        ),
    ]
