"""Add 14 new columns to Suggestion for FR-099 through FR-105 ranking signals.

- 7 score_<signal> FloatField columns (default 0.0) storing the raw signal value
- 7 <signal>_diagnostics JSONField columns (default dict) storing the
  explainable blob: raw input values, fallback flag, C++/Python path.

Defaults use 0.0 (neutral) not 0.5 — these signals are additive bonuses or
penalties, not bidirectional similarities. A weight of 0 produces a final
contribution of 0.

See docs/specs/fr099-*.md through docs/specs/fr105-*.md for the field
semantics and neutral-fallback behavior.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0035_upsert_fr099_fr105_defaults"),
    ]

    operations = [
        # FR-099 DARB
        migrations.AddField(
            model_name="suggestion",
            name="score_darb",
            field=models.FloatField(
                default=0.0,
                help_text="FR-099 Dangling Authority Redistribution Bonus. Boost when host has high content-value and low out-degree. 0.0 = neutral.",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="darb_diagnostics",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Explainable FR-099 dangling-authority-redistribution diagnostics (raw_host_value, out_degree, saturation, fallback reason).",
            ),
        ),
        # FR-100 KMIG
        migrations.AddField(
            model_name="suggestion",
            name="score_kmig",
            field=models.FloatField(
                default=0.0,
                help_text="FR-100 Katz Marginal Information Gain. 1.0 when host cannot reach dest via existing 1-2 hop paths; lower when already reachable. 0.0 = neutral.",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="kmig_diagnostics",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Explainable FR-100 Katz marginal-information-gain diagnostics (katz_2hop_reachability, direct_edge, two_hop_paths_count, beta).",
            ),
        ),
        # FR-101 TAPB
        migrations.AddField(
            model_name="suggestion",
            name="score_tapb",
            field=models.FloatField(
                default=0.0,
                help_text="FR-101 Tarjan Articulation Point Boost. 1.0 when host is a graph articulation point (cut vertex); 0.0 otherwise. 0.0 = neutral.",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="tapb_diagnostics",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Explainable FR-101 articulation-point diagnostics (is_articulation_point, graph_node_count, articulation_point_count).",
            ),
        ),
        # FR-102 KCIB
        migrations.AddField(
            model_name="suggestion",
            name="score_kcib",
            field=models.FloatField(
                default=0.0,
                help_text="FR-102 K-Core Integration Boost. Rewards high-kcore host linking to low-kcore dest to integrate periphery. 0.0 = neutral.",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="kcib_diagnostics",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Explainable FR-102 k-core-integration diagnostics (host_kcore, dest_kcore, max_kcore, kcore_delta).",
            ),
        ),
        # FR-103 BERP
        migrations.AddField(
            model_name="suggestion",
            name="score_berp",
            field=models.FloatField(
                default=0.0,
                help_text="FR-103 Bridge-Edge Redundancy Penalty. Negative when host->dest edge would be a new bridge (fragile single-path connector). 0.0 = neutral.",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="berp_diagnostics",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Explainable FR-103 bridge-edge-redundancy diagnostics (host_bcc, dest_bcc, would_create_bridge, component sizes).",
            ),
        ),
        # FR-104 HGTE
        migrations.AddField(
            model_name="suggestion",
            name="score_hgte",
            field=models.FloatField(
                default=0.0,
                help_text="FR-104 Host-Graph Topic Entropy Boost. Shannon-entropy-delta reward when adding the link diversifies host's outbound silo distribution. 0.0 = neutral.",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="hgte_diagnostics",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Explainable FR-104 host-topic-entropy diagnostics (host_out_degree, silo counts before/after, entropy delta).",
            ),
        ),
        # FR-105 RSQVA
        migrations.AddField(
            model_name="suggestion",
            name="score_rsqva",
            field=models.FloatField(
                default=0.0,
                help_text="FR-105 Reverse Search-Query Vocabulary Alignment. TF-IDF cosine of host vs dest GSC query vocabularies. 0.0 = neutral (no shared queries).",
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="rsqva_diagnostics",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Explainable FR-105 reverse-search-query alignment diagnostics (cosine, host_query_count, dest_query_count, shared_query_count).",
            ),
        ),
    ]
