"""Add cross-source content dedup support to ContentItem (masterplan Group A.6).

Two related schema changes:

1. ``content_hash`` gets a database index. Today the column is unindexed,
   so the dedup lookup at import time would do a full table scan. With
   ~50k+ ContentItem rows on a typical mid-sized forum + WP install,
   that's a non-trivial cost on every import. A B-tree on a 64-char
   SHA-256 hex column is roughly 4 MB at 50k rows — cheap.

2. New ``duplicate_of`` ForeignKey to self. When the same article gets
   imported from both XenForo (forum thread) and WordPress (blog post),
   the second copy points at the first one's row instead of regenerating
   the embedding. ``on_delete=SET_NULL`` so deleting the canonical row
   nulls the duplicate's pointer — the next embedding pass picks up the
   orphaned duplicate via the existing ``embedding_text_hash`` filter
   (Group D.2 plumbing).

No data backfill: existing rows have ``duplicate_of=NULL`` (no
duplicates detected yet). Future imports populate the field as
duplicates arrive.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0031_contentitem_pq_code_contentitem_pq_code_version"),
    ]

    operations = [
        # 1) Add the DB index to content_hash.
        migrations.AlterField(
            model_name="contentitem",
            name="content_hash",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "SHA-256 hash of the raw post body, used to detect edits AND to "
                    "find cross-source duplicates (Group A.6). Indexed so the dedup "
                    "lookup at import time is O(log N), not a full table scan."
                ),
                max_length=64,
            ),
        ),
        # 2) Add the duplicate_of ForeignKey.
        migrations.AddField(
            model_name="contentitem",
            name="duplicate_of",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "If set, this row was detected as a content duplicate of the "
                    "linked ContentItem during import (matching content_hash). "
                    "Embedding generation skips rows where this is set — they reuse "
                    "the parent's embedding via this FK at retrieval time."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="duplicates",
                to="content.contentitem",
            ),
        ),
    ]
