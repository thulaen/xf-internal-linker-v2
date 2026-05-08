# Monthly Top-50 Link Suggestions — prompt template

Used by the Claude Code path (Strategy A) of the monthly Top-50 job.
The pure-Python path (Strategy B) lives in
`backend/apps/pipeline/services/monthly_picker.py` and applies the same
editorial rules deterministically.

Substitute `{{MONTH}}` with the target month in `YYYY-MM` form before running.

---

## Prompt

Find the top 50 internal link suggestions for {{MONTH}}.

Steps:
1. Call `get_top_candidates(month='{{MONTH}}', n=300)` via the
   `xf-internal-linker` MCP server.
2. From those 300 candidates, pick 50 using these editorial rules:
   - **Diversity**: at most 3 suggestions per source thread (`source_thread_id`).
   - **Anchor variety**: at most 2 suggestions sharing the same anchor phrase.
   - **Score floor**: `composite_score >= 0.70`.
   - **Freshness bias**: prefer source posts younger than 90 days.
3. Write the report to `docs/reports/monthly-suggestions-{{MONTH}}.md`:
   - Group by `cluster_label`.
   - Per pick include: source post title, target post title, anchor phrase,
     composite score, and one short sentence on why it's a good pick.
4. End the report with a one-paragraph summary of how this month's picks
   differ from last month's (if a prior report exists).

The Python fallback uses the same rules + a deterministic per-pick
explanation built from the score breakdown rather than a generated sentence.
Either way the output file path is identical.
