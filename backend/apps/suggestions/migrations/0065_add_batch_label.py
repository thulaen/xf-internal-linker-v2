"""Migration: add batch_label + 'proposed' status to Suggestion.

Both fields back the monthly Top-50 picker:
- `batch_label` (YYYY-MM) lets the picker dedup across months and lets the
  Monthly Reports page filter the DB rows that backed each markdown file.
- The new `'proposed'` status differentiates AI-picked suggestions awaiting
  human review from the broader `'pending'` queue (which contains everything
  the pipeline emits, regardless of whether the AI has highlighted it).

Hand-rolled (not auto-generated) so the index name is explicit and the
choices change is documented inline.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0064_seed_w_embedding_age"),
    ]

    operations = [
        migrations.AddField(
            model_name="suggestion",
            name="batch_label",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "Optional batch tag stamped by the monthly Top-50 picker "
                    "(format YYYY-MM). Used for per-month dedup and to filter "
                    "the Monthly Reports page."
                ),
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="suggestion",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Review"),
                    ("proposed", "Proposed (AI-picked, awaiting human review)"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("applied", "Applied"),
                    ("verified", "Verified"),
                    ("stale", "Stale"),
                    ("superseded", "Superseded"),
                ],
                db_index=True,
                default="pending",
                help_text="Current review/lifecycle status of this suggestion.",
                max_length=20,
            ),
        ),
    ]
