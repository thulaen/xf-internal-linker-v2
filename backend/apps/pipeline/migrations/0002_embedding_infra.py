"""Migration: embedding-provider infrastructure tables (plan Parts 1, 4, 9).

Creates:
    EmbeddingCostLedger    -> per-(job_id, provider) token + cost accounting
    EmbeddingBakeoffResult -> per-run MRR/NDCG/Recall for each provider
    EmbeddingGateDecision  -> quality-gate decision log

Each table uses unique constraints where duplicates would be incorrect
(cost ledger + bake-off result) so resumed / re-run tasks upsert rather than
append, protecting against pile-up.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline", "0001_add_job_lease"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmbeddingCostLedger",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("job_id", models.CharField(db_index=True, max_length=64)),
                ("provider", models.CharField(db_index=True, max_length=32)),
                ("signature", models.CharField(max_length=64)),
                ("items", models.IntegerField(default=0)),
                ("tokens_input", models.BigIntegerField(default=0)),
                (
                    "cost_usd",
                    models.DecimalField(decimal_places=6, default=0, max_digits=12),
                ),
            ],
            options={
                "verbose_name": "Embedding Cost Ledger",
                "verbose_name_plural": "Embedding Cost Ledgers",
                "unique_together": {("job_id", "provider")},
            },
        ),
        migrations.AddIndex(
            model_name="embeddingcostledger",
            index=models.Index(
                fields=["provider", "-created_at"], name="pipeline_emb_prov_cr_idx"
            ),
        ),
        migrations.CreateModel(
            name="EmbeddingBakeoffResult",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("job_id", models.CharField(db_index=True, max_length=64)),
                ("provider", models.CharField(max_length=32)),
                ("signature", models.CharField(max_length=64)),
                ("sample_size", models.IntegerField(default=0)),
                (
                    "mrr_at_10",
                    models.DecimalField(decimal_places=4, default=0, max_digits=6),
                ),
                (
                    "ndcg_at_10",
                    models.DecimalField(decimal_places=4, default=0, max_digits=6),
                ),
                (
                    "recall_at_10",
                    models.DecimalField(decimal_places=4, default=0, max_digits=6),
                ),
                (
                    "mean_positive_cosine",
                    models.DecimalField(decimal_places=4, default=0, max_digits=6),
                ),
                (
                    "mean_negative_cosine",
                    models.DecimalField(decimal_places=4, default=0, max_digits=6),
                ),
                (
                    "separation_score",
                    models.DecimalField(decimal_places=4, default=0, max_digits=6),
                ),
                (
                    "cost_usd",
                    models.DecimalField(decimal_places=6, default=0, max_digits=10),
                ),
                ("latency_ms_p50", models.IntegerField(default=0)),
                ("latency_ms_p95", models.IntegerField(default=0)),
            ],
            options={
                "verbose_name": "Embedding Bake-off Result",
                "verbose_name_plural": "Embedding Bake-off Results",
                "unique_together": {("job_id", "provider")},
            },
        ),
        migrations.AddIndex(
            model_name="embeddingbakeoffresult",
            index=models.Index(fields=["-created_at"], name="pipeline_bakeoff_cr_idx"),
        ),
        migrations.CreateModel(
            name="EmbeddingGateDecision",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("item_id", models.IntegerField(db_index=True)),
                ("item_kind", models.CharField(max_length=16)),
                ("old_signature", models.CharField(blank=True, max_length=64)),
                ("new_signature", models.CharField(max_length=64)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("REPLACE", "Replace"),
                            ("REJECT", "Reject"),
                            ("NOOP", "No-op"),
                            ("ACCEPT_NEW", "Accept new"),
                        ],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("reason", models.CharField(max_length=64)),
                (
                    "score_delta",
                    models.DecimalField(decimal_places=6, default=0, max_digits=8),
                ),
            ],
            options={
                "verbose_name": "Embedding Gate Decision",
                "verbose_name_plural": "Embedding Gate Decisions",
            },
        ),
        migrations.AddIndex(
            model_name="embeddinggatedecision",
            index=models.Index(
                fields=["-created_at", "action"], name="pipeline_gate_cr_act_idx"
            ),
        ),
    ]
