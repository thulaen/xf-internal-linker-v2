"""Phase 0.4 — seed the full FR-053 spec §8 setting set into the Recommended preset.

The previous shipped defaults only wired four FR-053 keys (``enabled``,
``ranking_weight``, ``passages_per_page_max``, ``passage_words``,
``index_quantised``). The FR-053 specification §8 calls for an additional
eight keys controlling the OPQ + IVF retrieval index. Without them, the
``ivf_index`` C++ extension and the ``opq_trainer`` Celery task have no
operator-visible knobs and the Recommended preset cannot turn them on.

Citations:
    * OPQ:   Patent US 8,447,765 B2 (Microsoft, 2013); Jegou et al. 2010 TPAMI
             "Product quantization for nearest neighbor search".
    * IVFADC: Jegou-Douze-Schmid 2010 CVPR; FAISS-IVFADC reference impl.
    * IVF:   Sivic-Zisserman 2003 ICCV "Video Google" (inverted file).
    * Overlap: Callan 1994 SIGIR §5 (20-30% window overlap optimal).

Existing operator-overridden ``AppSetting`` values are NOT touched — only
the ``WeightPreset["Recommended"].weights`` JSONB seed is updated. Operators
who explicitly set their own values keep them. Fresh installs and pristine
installs that re-apply the Recommended preset get the new keys.

Values match ``backend/apps/suggestions/recommended_weights_forward_settings.py``
byte-for-byte.
"""

from django.db import migrations


NEW_VALUES = {
    "passage_relevance.opq_index_enabled": "true",
    "passage_relevance.opq_codebook_size": "64",
    "passage_relevance.opq_centroids_per_subquantiser": "256",
    "passage_relevance.ivf_n_centroids": "4096",
    "passage_relevance.ivf_nprobe": "16",
    "passage_relevance.passage_overlap_ratio": "0.25",
    "passage_relevance.host_scan_word_limit": "0",
    "passage_relevance.page_embedding_max_chars": "32000",
}


def seed_passage_relevance_defaults(apps, schema_editor):
    WeightPreset = apps.get_model("suggestions", "WeightPreset")
    AppSetting = apps.get_model("core", "AppSetting")

    preset, _ = WeightPreset.objects.get_or_create(
        name="Recommended",
        defaults={"is_system": True, "weights": dict(NEW_VALUES)},
    )
    weights = dict(preset.weights or {})
    weights.update(NEW_VALUES)
    preset.is_system = True
    preset.weights = weights
    preset.save(update_fields=["is_system", "weights", "updated_at"])

    # Seed AppSetting rows so the live runtime sees the values without
    # requiring an operator click on "Re-apply Recommended preset". Only
    # creates the row if it does not already exist; never overwrites an
    # operator-set value.
    for key, value in NEW_VALUES.items():
        AppSetting.objects.get_or_create(
            key=key,
            defaults={"value": value},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0057_seed_harmonious_g_aho_corasick"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_passage_relevance_defaults,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
