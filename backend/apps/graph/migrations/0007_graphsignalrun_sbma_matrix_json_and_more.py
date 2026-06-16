from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("graph", "0006_nodegraphsignal_icpc_degrees"),
    ]

    operations = [
        migrations.AddField(
            model_name="graphsignalrun",
            name="sbma_matrix_json",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="SBMA block-to-block link probability matrix for this run.",
            ),
        ),
        migrations.AddField(
            model_name="nodegraphsignal",
            name="sbma_block_id",
            field=models.IntegerField(
                blank=True,
                help_text="SBMA structural block assigned to this content item.",
                null=True,
            ),
        ),
    ]
