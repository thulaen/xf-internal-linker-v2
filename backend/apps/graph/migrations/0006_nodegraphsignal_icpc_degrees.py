from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("graph", "0005_graphsignalrun_linkpredictioncandidate_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="nodegraphsignal",
            name="icpc_local_indegree",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Incoming links from the same large-enough Louvain community.",
            ),
        ),
        migrations.AddField(
            model_name="nodegraphsignal",
            name="icpc_global_indegree",
            field=models.PositiveIntegerField(
                default=0,
                help_text="All incoming links to this content item in the graph snapshot.",
            ),
        ),
    ]
