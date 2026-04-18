"""Backfill runtime anti-spam defaults into the Recommended preset.

Existing installs already have a Recommended preset row, so changing the
hardcoded defaults is not enough. This migration updates the preset in place so
FR-045, FR-197, and FR-198 are enabled by default with conservative non-zero
starting weights.
"""

from django.db import migrations


NEW_VALUES = {
    "anchor_diversity.enabled": "true",
    "anchor_diversity.ranking_weight": "0.03",
    "anchor_diversity.min_history_count": "3",
    "anchor_diversity.max_exact_match_share": "0.40",
    "anchor_diversity.max_exact_match_count": "3",
    "anchor_diversity.hard_cap_enabled": "false",
    "keyword_stuffing.enabled": "true",
    "keyword_stuffing.ranking_weight": "0.04",
    "keyword_stuffing.alpha": "6.0",
    "keyword_stuffing.tau": "0.30",
    "keyword_stuffing.dirichlet_mu": "2000",
    "keyword_stuffing.top_k_stuff_terms": "5",
    "link_farm.enabled": "true",
    "link_farm.ranking_weight": "0.03",
    "link_farm.min_scc_size": "3",
    "link_farm.density_threshold": "0.6",
    "link_farm.lambda": "0.8",
}


def upsert_runtime_antispam_defaults(apps, schema_editor):
    WeightPreset = apps.get_model("suggestions", "WeightPreset")

    preset, _ = WeightPreset.objects.get_or_create(
        name="Recommended",
        defaults={
            "is_system": True,
            "weights": dict(NEW_VALUES),
        },
    )

    weights = dict(preset.weights or {})
    weights.update(NEW_VALUES)
    preset.is_system = True
    preset.weights = weights
    preset.save(update_fields=["is_system", "weights", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0031_suggestion_anchor_diversity_diagnostics_and_more"),
    ]

    operations = [
        migrations.RunPython(
            upsert_runtime_antispam_defaults,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
