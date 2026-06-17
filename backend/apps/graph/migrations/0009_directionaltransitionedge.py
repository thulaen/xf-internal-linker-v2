from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0043_supersededembedding_unique_archive"),
        ("graph", "0008_nodegraphsignal_tosd_lambda"),
    ]

    operations = [
        migrations.CreateModel(
            name="DirectionalTransitionEdge",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("matomo", "Matomo"),
                            ("ga4", "Google Analytics 4"),
                            ("combined", "Deduped Matomo and Google Analytics 4"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("site_id", models.CharField(blank=True, db_index=True, max_length=32)),
                ("transition_count", models.PositiveIntegerField(default=0)),
                ("source_transition_count", models.PositiveIntegerField(default=0)),
                ("data_window_start", models.DateField()),
                ("data_window_end", models.DateField()),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                (
                    "dest_content_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dstp_incoming_transitions",
                        to="content.contentitem",
                    ),
                ),
                (
                    "source_content_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dstp_outgoing_transitions",
                        to="content.contentitem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Directional Transition Edge",
                "verbose_name_plural": "Directional Transition Edges",
                "indexes": [
                    models.Index(
                        fields=["source_content_item", "source"],
                        name="graph_direc_source__a176b6_idx",
                    ),
                    models.Index(
                        fields=["dest_content_item", "source"],
                        name="graph_direc_dest_co_5a4f79_idx",
                    ),
                    models.Index(
                        fields=["source", "data_window_end"],
                        name="graph_direc_source_01dd2d_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=[
                            "source",
                            "site_id",
                            "source_content_item",
                            "dest_content_item",
                        ],
                        name="graph_unique_directional_transition_edge",
                    )
                ],
            },
        ),
    ]
