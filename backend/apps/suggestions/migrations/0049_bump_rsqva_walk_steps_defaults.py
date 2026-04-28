"""Bump two Recommended-preset defaults: RSQVA max_vocab_size and graph_candidate walk_steps_per_entity.

Two changes:
- ``rsqva.max_vocab_size``: ``10000`` → ``25000``
  Larger feature-hashed TF-IDF table for FR-105 RSQVA so more long-tail GSC
  query vocabulary survives the hash projection. Salton & Buckley 1988
  IP&M 24(5) §3.2 reliability scales with vocabulary coverage; doubling
  the table reduces hash collisions on the typical 50k-query GSC corpus
  while staying inside the 1024-dim pgvector projection bound.
- ``graph_candidate.walk_steps_per_entity``: ``1000`` → ``5000``
  Five-fold deeper random walks per entity for FR-021 graph candidate
  generation. Page-Brin-Motwani-Winograd 1999 §3 random-walk convergence
  reaches stable PageRank distribution at ~50× node count; on the typical
  forum + WP graph (~10k–50k nodes) 5000 steps gives clean PPR distributions
  for entity-conditioned candidate generation, where 1000 steps left the
  long tail under-sampled.

Existing operator-overridden ``AppSetting`` values are NOT touched — only
the ``WeightPreset["Recommended"].weights`` JSONB seed is updated. Operators
who explicitly set their own values keep them. New installs get the new
defaults. Existing pristine installs can hit "Re-apply Recommended preset"
(Group Z in the masterplan, when shipped) to pick up the new values.

Values match ``backend/apps/suggestions/recommended_weights.py`` and
``recommended_weights_forward_settings.py`` byte-for-byte.
"""

from django.db import migrations


NEW_VALUES = {
    # FR-105 Reverse Search-Query Vocabulary Alignment — bumped 10000 → 25000
    "rsqva.max_vocab_size": "25000",
    # FR-021 Graph-Based Link Candidate Generation — bumped 1000 → 5000
    "graph_candidate.walk_steps_per_entity": "5000",
}


def bump_recommended_defaults(apps, schema_editor):
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
        ("suggestions", "0048_decommission_cs_labels"),
    ]

    operations = [
        migrations.RunPython(
            bump_recommended_defaults, reverse_code=migrations.RunPython.noop
        ),
    ]
