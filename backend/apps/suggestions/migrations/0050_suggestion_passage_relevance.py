"""Add Suggestion.score_passage_relevance + diagnostics for FR-053 (Group E).

Plain-English: when the ranker computes the best-passage similarity
for a destination, it stores the score (so score_final picks it up
as an additive contribution) and the diagnostic JSON (so the operator
can see WHICH passage matched and how similar it was) on every
``Suggestion`` row. This migration just adds the two columns; the
service that fills them in lives in
``apps/pipeline/services/passage_relevance.py``.

Defaults match the spec's neutral-fallback contract: 0.5 means
"feature inactive or no passages available", which contributes zero
to the additive component after centering.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0049_bump_rsqva_walk_steps_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="suggestion",
            name="score_passage_relevance",
            field=models.FloatField(
                default=0.5,
                help_text=(
                    "Bounded best-passage similarity score in [0.5, 1.0]. 0.5 = "
                    "neutral (no passage matched, feature off, or destination too "
                    "short). >0.5 = at least one passage in the destination is a "
                    "good semantic match for the host sentence. Patent US "
                    "9,940,367 B1 (Google 2018)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="suggestion",
            name="passage_relevance_diagnostics",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Explainable best-passage match details — best_passage_index, "
                    "best_passage_similarity, all_passage_similarities, "
                    "best_passage_preview, passage_count, state, and the chunk "
                    "settings used at index time. Operator review surface for "
                    "FR-053 per the spec's ## Diagnostics section."
                ),
            ),
        ),
    ]
