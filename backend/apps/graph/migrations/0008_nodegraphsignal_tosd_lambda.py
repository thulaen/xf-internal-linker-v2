from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("graph", "0007_graphsignalrun_sbma_matrix_json_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="nodegraphsignal",
            name="tosd_lambda",
            field=models.FloatField(
                blank=True,
                help_text="TOSD normalized-Laplacian variation value for this content item.",
                null=True,
            ),
        ),
    ]
