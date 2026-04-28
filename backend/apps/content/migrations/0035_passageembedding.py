"""Add ``PassageEmbedding`` for masterplan Group E / FR-053.

Plain-English purpose: long pages have one perfectly-relevant section
buried among less-relevant filler. The page-level embedding averages
that section away. ``PassageEmbedding`` stores ~200-token slices of
the page body so the ranker can compare a host sentence to the
BEST-matching passage instead of the whole page.

Storage cost: ~2 GB at 100k pages × 5 passages × 1024 dims × 4 bytes
(float32). V1 ships float32 pgvector; the int8-quantised FAISS path
is in the spec's ``## Pending`` list as a follow-up optimisation.

No data migration. The ``passage_relevance`` service writes rows on
import / re-embed pass. ``Sentence`` and ``Post`` are already in
place; this only adds the new ``PassageEmbedding`` model.
"""

import django.db.models.deletion
import pgvector.django.vector
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0034_contentitem_quotation_density"),
    ]

    operations = [
        migrations.CreateModel(
            name="PassageEmbedding",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "passage_index",
                    models.SmallIntegerField(
                        help_text=(
                            "Zero-based ordinal of the passage inside the page (0 = first, "
                            "1 = next, ...). Used for diagnostics like 'best_passage_index'."
                        ),
                    ),
                ),
                (
                    "text",
                    models.TextField(
                        help_text=(
                            "The passage text after chunking. Stored as plain text so the "
                            "best-passage diagnostic preview can show the matching paragraph "
                            "directly to operators in the suggestion-detail UI."
                        ),
                    ),
                ),
                (
                    "word_count",
                    models.IntegerField(
                        default=0,
                        help_text="Number of whitespace-tokenised words in the passage.",
                    ),
                ),
                (
                    "embedding",
                    pgvector.django.vector.VectorField(
                        blank=True,
                        help_text=(
                            "L2-normalised 1024-dim BGE-M3 embedding of the passage. NULL "
                            "until the embedding pass touches this row; ranker treats NULL "
                            "as the neutral fallback (no passage similarity contribution)."
                        ),
                        null=True,
                    ),
                ),
                (
                    "embedding_model_version",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text=(
                            "Model + preprocessing version that produced the embedding. "
                            "Used by the embed pass to skip rows already at the current "
                            "signature (matches ContentItem / Sentence convention)."
                        ),
                        max_length=64,
                    ),
                ),
                (
                    "embedding_text_hash",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text=(
                            "SHA-256 of the exact passage text passed to the model. "
                            "Re-embed fires when this hash drifts even if the model "
                            "signature is unchanged."
                        ),
                        max_length=64,
                    ),
                ),
                (
                    "passage_words_setting",
                    models.SmallIntegerField(
                        default=200,
                        help_text=(
                            "Value of `passage_relevance.passage_words` at chunk time. "
                            "Used to detect when the chunking parameter has changed and "
                            "the passages need to be regenerated."
                        ),
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content_item",
                    models.ForeignKey(
                        help_text="The page this passage was extracted from.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="passage_embeddings",
                        to="content.contentitem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Passage Embedding",
                "verbose_name_plural": "Passage Embeddings",
                "ordering": ["content_item", "passage_index"],
            },
        ),
        migrations.AddConstraint(
            model_name="passageembedding",
            constraint=models.UniqueConstraint(
                fields=("content_item", "passage_index"),
                name="unique_passage_per_content_item",
            ),
        ),
        migrations.AddIndex(
            model_name="passageembedding",
            index=models.Index(
                fields=["content_item", "passage_index"],
                name="content_pas_content_2c5cb1_idx",
            ),
        ),
    ]
