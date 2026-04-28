"""Add ``embedding_text_hash`` to ContentItem (masterplan Group D.2).

Plain-English purpose: today re-embedding only fires when the model
signature changes. If the operator edits a post body, the existing
content-hash check skips the re-embed because the embedding column
isn't NULL and the model signature still matches. The post's vector
silently goes stale.

This migration adds a column that stores the SHA-256 of the exact
text we last fed the model. The embedding generator (D.2 wiring in
``apps/pipeline/services/embeddings.py``) compares the new text's
hash against the stored one; if they differ, re-embed fires even
though the model is unchanged. If they match AND the model still
matches, the row is skipped — no duplicate row ever gets written
for unchanged content.

No data backfill: the column starts NULL/blank for every row. The
embed generator treats NULL as "must re-embed on next pass" so the
long tail picks up the new discipline gradually.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0032_contentitem_duplicate_of"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentitem",
            name="embedding_text_hash",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "SHA-256 hex digest of the exact text passed to the embedding model "
                    "(title + body + truncation). Re-embed fires whenever this hash drifts "
                    "OR the model signature drifts. NULL/blank means the row has never been "
                    "embedded under the new hash discipline (Group D.2) — treated as 'must "
                    "re-embed' on next pass."
                ),
                max_length=64,
            ),
        ),
    ]
