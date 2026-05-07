"""FR-240 + FR-241 — flip lexical retriever and passage retrieval to default-on.

FR-240 (hybrid retrieval BM25 + RRF):
    The existing `LexicalRetriever` (Jaccard-style token overlap) plus
    the existing `_fuse_via_rrf` fusion in `candidate_retrievers.py` are
    the v1 hybrid path. The retriever is gated on the AppSetting
    `stage1.lexical_retriever_enabled` (read by `_setting_enabled` which
    falls back to False when no row exists). This migration seeds the
    row to True so the retriever runs default-on.

FR-241 (passage retrieval default-on):
    `passage_relevance.enabled` is read via `setting_bool(..., True)`
    in `passage_relevance.py:101` and `:493` — already default-True
    when no AppSetting row exists. Seeding the row makes the value
    visible to operators on `/settings` so they can override it; no
    behavioural change. This migration also seeds the supporting
    `passage_relevance.ranking_weight` from FR-053 spec §8.

Citations are inline in `apps.suggestions.recommended_weights` and the
parent fr237..fr250 migration (0061). Existing operator-overridden
AppSettings are NOT touched — only `get_or_create` is used.
"""

from django.db import migrations


NEW_VALUES = {
    # FR-240
    "stage1.lexical_retriever_enabled": "true",
    # FR-241 — visible-to-operator sentinel; behaviour unchanged
    "passage_relevance.enabled": "true",
    "passage_relevance.ranking_weight": "0.10",
}


def seed_fr240_fr241_defaults(apps, schema_editor):
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
        ("suggestions", "0061_seed_fr237_through_fr250_defaults"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_fr240_fr241_defaults,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
