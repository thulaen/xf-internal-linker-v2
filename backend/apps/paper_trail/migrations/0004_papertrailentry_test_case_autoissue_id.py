"""Paper Trail Evidence Rule (added 2026-05-17).

Adds `test_case_autoissue_id` to PaperTrailEntry so new entries (from
2026-05-17 onward) can link to the `AutoIssue(category='test_case')` row
that captures the full agent-readable contract. The field is nullable to
grandfather every existing row; the validator that requires it on new
rows lives in `PaperTrailEntry._validate()`.

Spec: docs/PAPER-TRAIL-EVIDENCE-RULE.md
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("paper_trail", "0003_remove_papertrailentry_uniq_papertrail_active_category_fingerprint_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="papertrailentry",
            name="test_case_autoissue_id",
            field=models.IntegerField(
                null=True,
                blank=True,
                db_index=True,
                help_text=(
                    "PK of the AutoIssue(category='test_case') row whose "
                    "lessons_learned carries the full 10-field BDD contract "
                    "for this entry. Required on entries deferred_at >= "
                    "2026-05-17 per docs/PAPER-TRAIL-EVIDENCE-RULE.md."
                ),
            ),
        ),
    ]
