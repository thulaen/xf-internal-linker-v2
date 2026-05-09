"""Add ``kind`` field to RankingChallenger for FR-018b meta-algorithm tuning.

Distinguishes ranking-blend-weight challengers (FR-018, the original
``w_semantic`` / ``w_keyword`` / ``w_node`` / ``w_quality`` keys) from
meta-algorithm-parameter challengers (FR-018b — RRF k, BM25 k1/b, MMR
lambda, etc.). Both use the same table + SPRT evaluator pipeline; the
``kind`` discriminator just keeps audit queries clean.

Default ``"weights"`` preserves the existing semantics for any rows
created before this migration ran.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0066_seed_xenforo_bm25_default_on"),
    ]

    operations = [
        migrations.AddField(
            model_name="rankingchallenger",
            name="kind",
            field=models.CharField(
                choices=[
                    ("weights", "Ranking-blend weights (FR-018)"),
                    ("meta_algorithm", "Meta-algorithm parameter (FR-018b)"),
                ],
                db_index=True,
                default="weights",
                help_text=(
                    "Distinguishes ranking-blend-weight challengers (FR-018, "
                    "the original four w_* keys) from meta-algorithm-"
                    "parameter challengers (FR-018b, things like RRF k / "
                    "BM25 k1 / MMR lambda). Both use the same model and the "
                    "same SPRT evaluator, but distinct kinds keep audit "
                    "queries clear."
                ),
                max_length=32,
            ),
        ),
    ]
