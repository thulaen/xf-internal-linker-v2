"""Flip ``stage1.xenforo_bm25_retriever_enabled`` to default-on.

The XenForo BM25 retriever (Path A — REST API) ships with the existing
XenForo API key; no new credentials needed. It calls XenForo's Enhanced
Search ``/api/search/`` endpoint per destination and contributes BM25-
ranked candidates that fuse with the FAISS results via RRF (Cormack et
al. 2009 SIGIR — already implemented in
``apps.pipeline.services.reciprocal_rank_fusion``).

Cold-start safety: if ``XENFORO_BASE_URL`` / ``XENFORO_API_KEY`` are
missing or wrong, the retriever logs and returns empty contributions
rather than raising — see
``XenForoBM25Retriever._resolve_client`` in
``backend/apps/pipeline/services/candidate_retrievers.py``.

Citations: BM25 — Robertson & Zaragoza (2009) *Foundations and Trends
in IR* 3(4); RRF — Cormack et al. SIGIR'09. Spec:
``docs/specs/xf-bm25-retrieval.md``.

Existing operator-overridden AppSettings are NOT touched — only
``get_or_create`` is used. Mirrors the FR-240 default-on pattern in
migration ``0062_seed_fr240_fr241_default_on.py``.
"""

from django.db import migrations


NEW_VALUES = {
    "stage1.xenforo_bm25_retriever_enabled": "true",
}


def seed_xenforo_bm25_default(apps, schema_editor):
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
        ("suggestions", "0065_add_batch_label"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_xenforo_bm25_default,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
