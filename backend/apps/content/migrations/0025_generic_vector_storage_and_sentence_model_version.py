from django.db import migrations, models
from pgvector.django import VectorField


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_EMBEDDING_DIM = 1024
CONTENT_ITEM_HNSW_INDEX = "content_item_embedding_hnsw_idx"
SENTENCE_HNSW_INDEX = "sentence_embedding_hnsw_idx"


def _current_embedding_signature(apps) -> str:
    AppSetting = apps.get_model("core", "AppSetting")
    RuntimeModelRegistry = None
    try:
        RuntimeModelRegistry = apps.get_model("core", "RuntimeModelRegistry")
    except LookupError:
        RuntimeModelRegistry = None

    model_name = DEFAULT_EMBEDDING_MODEL
    dimension = DEFAULT_EMBEDDING_DIM

    champion = None
    if RuntimeModelRegistry is not None:
        champion = (
            RuntimeModelRegistry.objects.filter(
                task_type="embedding",
                role="champion",
            )
            .exclude(status="deleted")
            .order_by("-promoted_at", "-id")
            .first()
        )
    if champion is not None:
        if champion.model_name:
            model_name = champion.model_name
        if champion.dimension:
            dimension = champion.dimension

    setting_value = (
        AppSetting.objects.filter(key="embedding_model")
        .values_list("value", flat=True)
        .first()
    )
    if setting_value:
        model_name = str(setting_value)

    return f"{model_name}:{int(dimension)}"


def backfill_embedding_model_versions(apps, schema_editor):
    ContentItem = apps.get_model("content", "ContentItem")
    Sentence = apps.get_model("content", "Sentence")
    SupersededEmbedding = apps.get_model("content", "SupersededEmbedding")

    signature = _current_embedding_signature(apps)

    ContentItem.objects.filter(
        embedding__isnull=False,
        embedding_model_version="",
    ).update(embedding_model_version=signature)
    Sentence.objects.filter(
        embedding__isnull=False,
        embedding_model_version="",
    ).update(embedding_model_version=signature)
    SupersededEmbedding.objects.filter(
        embedding__isnull=False,
        embedding_model_version="",
    ).update(embedding_model_version=signature)


def noop_reverse(apps, schema_editor):
    """Backfill is intentionally one-way."""


def drop_fixed_dimension_hnsw_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP INDEX IF EXISTS {CONTENT_ITEM_HNSW_INDEX};")
    schema_editor.execute(f"DROP INDEX IF EXISTS {SENTENCE_HNSW_INDEX};")


def recreate_fixed_dimension_hnsw_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS "
        f"{CONTENT_ITEM_HNSW_INDEX} "
        "ON content_contentitem USING hnsw (embedding vector_cosine_ops);"
    )
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS "
        f"{SENTENCE_HNSW_INDEX} "
        "ON content_sentence USING hnsw (embedding vector_cosine_ops);"
    )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("content", "0024_slice5_score_diagnostics"),
        ("core", "0011_seed_default_embedding_model"),
    ]

    operations = [
        migrations.RunPython(
            drop_fixed_dimension_hnsw_indexes,
            recreate_fixed_dimension_hnsw_indexes,
        ),
        migrations.AddField(
            model_name="sentence",
            name="embedding_model_version",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "Model + preprocessing version that produced the current "
                    "sentence embedding. Used to keep stage-2 similarity aligned "
                    "with the active embedding model."
                ),
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="contentitem",
            name="embedding",
            field=VectorField(
                blank=True,
                help_text=(
                    "Semantic embedding for the active model. Pair with "
                    "embedding_model_version when reading."
                ),
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="sentence",
            name="embedding",
            field=VectorField(
                blank=True,
                help_text=(
                    "Sentence embedding for the active model. Used in stage-2 "
                    "similarity ranking."
                ),
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="supersededembedding",
            name="embedding",
            field=VectorField(
                blank=True,
                help_text="The old embedding vector that was replaced.",
                null=True,
            ),
        ),
        migrations.RunPython(backfill_embedding_model_versions, noop_reverse),
    ]
