"""Drop MetaTournamentResult and HoldoutQuery tables.

The FR-225 meta tournament system was retired in favour of a fixed 52-meta
roster and the Scheduled Updates orchestrator. This migration deletes the two
tables that tracked tournament holdout queries and per-meta NDCG outcomes.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0033_add_rejected_pair"),
    ]

    operations = [
        migrations.DeleteModel(name="MetaTournamentResult"),
        migrations.DeleteModel(name="HoldoutQuery"),
    ]
