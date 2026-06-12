"""Seed ``stage1.tantivy_bm25_retriever_enabled`` default-on.

The Tantivy BM25 retriever runs entirely in-process: it builds a
keyword index in memory from host titles on every pipeline pass and
ranks candidates with Okapi BM25. It needs no external data, no
credentials, and no separate server, so the default-on rule applies
with no exemption. Cold-start safety: an empty corpus, an empty query,
or a missing ``tantivy`` package all make the retriever contribute
nothing for that pass instead of raising — see
``TantivyBM25Retriever.retrieve`` in
``backend/apps/pipeline/services/candidate_retrievers.py``.

Citations: BM25 — Robertson & Zaragoza (2009) *Foundations and Trends
in IR* 3(4); RRF — Cormack et al. SIGIR'09; Tantivy as the approved
JVM-free Lucene-style index —
``docs/specs/fr-approved-library-expansion-bank.md`` § "Need full-text
search without JVM".

Existing operator-overridden AppSettings are NOT touched — only
``get_or_create`` is used. Mirrors the XF-BM25 default-on pattern in
migration ``0066_seed_xenforo_bm25_default_on.py``.
"""

from django.db import migrations


NEW_VALUES = {
    "stage1.tantivy_bm25_retriever_enabled": "true",
}


def seed_tantivy_bm25_default(apps, schema_editor):
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

    for key, value in NEW_VALUES.items():
        AppSetting.objects.get_or_create(
            key=key,
            defaults={"value": value},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0069_extend_field_aware_early_content_defaults"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_tantivy_bm25_default,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
