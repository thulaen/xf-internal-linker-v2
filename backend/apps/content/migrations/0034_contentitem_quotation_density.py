"""Add ``quotation_density`` to ContentItem (masterplan Group D.4).

Plain-English purpose: capture how much of a post's raw body lived
inside ``[QUOTE]`` blocks before they got stripped. A post that's
80 % quotation is "compiled" content rather than authored — useful
as a future originality signal (FR-041 Originality Provenance
Scoring is pending; this column gives it a concrete first feature).

Today the column is store-only — no ranking signal consumes it.
Default 0.0 for existing rows; the importer back-fills the real
value on the next re-import touch.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0033_contentitem_embedding_text_hash"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentitem",
            name="quotation_density",
            field=models.FloatField(
                default=0.0,
                help_text=(
                    "Quotation density (Group D.4) — quoted_chars / total_chars from "
                    "the raw post body before BBCode stripping. Future input to "
                    "FR-041 originality scoring; not used in ranking today."
                ),
            ),
        ),
    ]
