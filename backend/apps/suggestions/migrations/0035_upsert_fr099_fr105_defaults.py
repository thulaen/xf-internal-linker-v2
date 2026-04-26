"""Upsert FR-099 through FR-105 ranking-signal defaults into the Recommended preset.

Adds 19 keys covering the 7 new graph-topology ranking signals:
- FR-099 Dangling Authority Redistribution Bonus (DARB)
- FR-100 Katz Marginal Information Gain (KMIG)
- FR-101 Tarjan Articulation Point Boost (TAPB)
- FR-102 K-Core Integration Boost (KCIB)
- FR-103 Bridge-Edge Redundancy Penalty (BERP)
- FR-104 Host-Graph Topic Entropy Boost (HGTE)
- FR-105 Reverse Search-Query Vocabulary Alignment (RSQVA)

Every default is cited to a specific paper section/table in the matching
spec under docs/specs/fr099-*.md through docs/specs/fr105-*.md. Values
match backend/apps/suggestions/recommended_weights.py byte-for-byte.

Gate A (implementation) and Gate B (user-idea) from docs/RANKING-GATES.md
were applied to every key below; see each FR spec's
## Gate Justifications section.
"""

from django.db import migrations


NEW_VALUES = {
    # FR-099 Dangling Authority Redistribution Bonus
    # Baseline: Page, Brin, Motwani, Winograd 1999, Stanford InfoLab 1999-66 §2.5 + §3.2 eq. 1
    "darb.enabled": "true",
    "darb.ranking_weight": "0.04",
    "darb.out_degree_saturation": "5",
    "darb.min_host_value": "0.5",
    # FR-100 Katz Marginal Information Gain
    # Baseline: Katz 1953, Psychometrika 18(1) §2 eq. 2 + §3; β=0.5 from Pigueiral 2017 EuroCG'17
    "kmig.enabled": "true",
    "kmig.ranking_weight": "0.05",
    "kmig.attenuation": "0.5",
    "kmig.max_hops": "2",
    # FR-101 Tarjan Articulation Point Boost
    # Baseline: Tarjan 1972, SIAM J. Computing 1(2) §3 eq. 3.2
    "tapb.enabled": "true",
    "tapb.ranking_weight": "0.03",
    "tapb.apply_to_articulation_node_only": "true",
    # FR-102 K-Core Integration Boost
    # Baseline: Seidman 1983, Social Networks 5(3) §2 eq. 1; Batagelj-Zaversnik 2003 O(m) algorithm
    "kcib.enabled": "true",
    "kcib.ranking_weight": "0.03",
    "kcib.min_kcore_spread": "1",
    # FR-103 Bridge-Edge Redundancy Penalty
    # Baseline: Hopcroft & Tarjan 1973, CACM 16(6) §2 Algorithm 3
    "berp.enabled": "true",
    "berp.ranking_weight": "0.04",
    "berp.min_component_size": "5",
    # FR-104 Host-Graph Topic Entropy Boost
    # Baseline: Shannon 1948, Bell System Tech Journal 27(3) §6 eq. 4
    "hgte.enabled": "true",
    "hgte.ranking_weight": "0.04",
    "hgte.min_host_out_degree": "3",
    # FR-105 Reverse Search-Query Vocabulary Alignment
    # Baseline: Salton & Buckley 1988, IP&M 24(5) §3 eq. 1 + §4 cosine;
    # Järvelin-Kekäläinen 2002 ACM TOIS 20(4) §2.1 click-weighted CG
    "rsqva.enabled": "true",
    "rsqva.ranking_weight": "0.05",
    "rsqva.min_queries_per_page": "5",
    "rsqva.min_query_clicks": "1",
    "rsqva.max_vocab_size": "10000",
}


def upsert_fr099_fr105_defaults(apps, schema_editor):
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
        ("suggestions", "0034_drop_meta_tournament_tables"),
    ]

    operations = [
        migrations.RunPython(
            upsert_fr099_fr105_defaults, reverse_code=migrations.RunPython.noop
        ),
    ]
