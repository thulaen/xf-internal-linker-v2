"""Add FR-105 RSQVA input: gsc_query_tfidf_vector pgvector column on ContentItem.

L2-normalized TF-IDF vector over each page's GSC query vocabulary,
projected to 1024-dim via feature hashing (bounded by rsqva.max_vocab_size
default 10000 but hashed to 1024 to keep pgvector compatibility with the
existing embedding dimension).

Rebuilt daily by analytics.tasks.refresh_gsc_query_tfidf Celery Beat task.
Null until first sync — FR-105's neutral fallback handles the bootstrap
period (returns 0.0 score with diagnostic 'rsqva: vector_not_computed').

See docs/specs/fr105-reverse-search-query-vocabulary-alignment.md for the
TF-IDF construction + Salton & Buckley 1988 + Järvelin-Kekäläinen 2002
source of truth.
"""

from django.db import migrations
import pgvector.django


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0025_generic_vector_storage_and_sentence_model_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentitem",
            name="gsc_query_tfidf_vector",
            field=pgvector.django.VectorField(
                blank=True,
                dimensions=1024,
                null=True,
                help_text=(
                    "FR-105 RSQVA: L2-normalized TF-IDF vector over this page's "
                    "GSC query vocabulary, projected to 1024-dim via feature "
                    "hashing. Null until first analytics sync."
                ),
            ),
        ),
    ]
