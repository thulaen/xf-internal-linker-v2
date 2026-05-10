"""Adds the 4-tuple UniqueConstraint to SupersededEmbedding archive table.

Closes AutoIssue #9 + RPT-004 row 2 (NO-DUPLICATES.md invariant).

`SupersededEmbedding` is the archive table that holds prior versions of
ContentItem.embedding when the embedding gets recomputed. Without a
unique constraint, the supersede pattern could pile up duplicate
archive rows on every retry, eating disk on the user's 59-GB-free box.

Safety check (run 2026-05-10): the live `content_supersededembedding`
table has 0 rows, so the new constraint cannot fail due to existing
data. Pure schema change.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0042_queue_orphan_reembed"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="supersededembedding",
            constraint=models.UniqueConstraint(
                fields=(
                    "content_item",
                    "embedding_model_version",
                    "content_hash",
                    "content_version",
                ),
                name="unique_superseded_embedding_archive",
            ),
        ),
    ]
