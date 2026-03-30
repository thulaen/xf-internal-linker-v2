# Weight Presets Operator Manual

## Overview

Weight presets are saved groups of ranking numbers.

Think of a preset like a saved recipe. It stores one value for every in-scope weight key. Loading a preset writes the live values to `AppSetting` all at once, so you do not end up half way between two setups.

Weight presets exist for three simple reasons:

- to give you a safe starting point
- to let you save named experiments
- to let you get back to a known-good setup fast

Phase 17 has two preset types:

- System presets are created by code. They are seeded by migration `0016_seed_recommended_preset.py`. They are read-only.
- User presets are snapshots saved by an operator from the current live weights. They can be loaded, renamed, and deleted.

The `Recommended` system preset is seeded on first install. The migration also writes those seeded values into `AppSetting`, so they are live right away.

Important: the `Recommended` preset is not the same thing as `PRESET_DEFAULTS` in `backend/apps/suggestions/weight_preset_service.py`. The `Recommended` preset is the researched starting profile. `PRESET_DEFAULTS` is the hardcoded safety net used when a preset JSON is missing a key.

## The Recommended Preset

The tables below list the seeded `Recommended` values from `backend/apps/suggestions/migrations/0016_seed_recommended_preset.py`. The key list was cross-checked against `backend/apps/suggestions/weight_preset_service.py`, which is the canonical preset registry.

Small code note: the request text says 54 keys, but the checked-in Phase 17 code currently defines 53 in-scope preset keys. The service registry and the seeding migration both list 53 keys, and the migration writes all 53 on first install.

For readability, the keys below are grouped into logical buckets. In storage, `clustering.*` and `silo.*` are still written under the `ml` `AppSetting` category.

### ml

| Key | Seeded value | Why this value |
| --- | --- | --- |
| `w_semantic` | `0.40` | Keep meaning-match as the biggest signal, but leave room for forum wording and structure. |
| `w_keyword` | `0.25` | Give exact words and forum jargon a real voice in the final score. |
| `w_node` | `0.20` | Reward links that stay inside the same section or topic area. |
| `w_quality` | `0.15` | Keep page quality useful without letting it overpower relevance. |
| `weighted_authority.ranking_weight` | `0.10` | Start gently so authority helps, but does not dominate day-one ranking. |
| `weighted_authority.position_bias` | `0.5` | Penalize later links a bit, but not so much that placement decides everything. |
| `weighted_authority.empty_anchor_factor` | `0.6` | Discount empty anchors, but do not throw them away completely. |
| `weighted_authority.bare_url_factor` | `0.35` | Strongly down-weight naked URLs because they are weak anchor text. |
| `weighted_authority.weak_context_factor` | `0.75` | Discount weak surrounding text while still keeping some credit. |
| `weighted_authority.isolated_context_factor` | `0.45` | Heavily discount isolated or list-like links that often have poor context. |
| `rare_term_propagation.enabled` | `true` | This is safe to leave on from day one and helps thin pages borrow rare terms. |
| `rare_term_propagation.ranking_weight` | `0.05` | Give rare-term help a small boost without letting it outrank stronger signals. |
| `rare_term_propagation.max_document_frequency` | `3` | Only very rare terms are shared across related pages. |
| `rare_term_propagation.minimum_supporting_related_pages` | `2` | Require more than one related page so one odd page does not decide. |
| `field_aware_relevance.ranking_weight` | `0.10` | Title and body alignment matter early, so give this a moderate voice. |
| `field_aware_relevance.title_field_weight` | `0.40` | Titles are usually the clearest short summary of a page. |
| `field_aware_relevance.body_field_weight` | `0.30` | Body text matters a lot, but titles still lead. |
| `field_aware_relevance.scope_field_weight` | `0.15` | Topic labels help, but they are supporting evidence, not the main proof. |
| `field_aware_relevance.learned_anchor_field_weight` | `0.15` | Existing anchor vocabulary helps, but it should stay a supporting signal. |
| `ga4_gsc.ranking_weight` | `0.00` | Cold start: leave analytics influence off until enough real data exists. |
| `click_distance.ranking_weight` | `0.07` | Add a light structure prior without letting site depth decide everything. |
| `click_distance.k_cd` | `4.0` | Make deep pages meaningfully different from shallow ones. |
| `click_distance.b_cd` | `0.75` | Smooth raw click-distance heavily so the signal stays stable. |
| `click_distance.b_ud` | `0.25` | Use URL depth as light extra evidence only. |
| `explore_exploit.enabled` | `false` | Cold start: keep feedback reranking off until there is enough review history. |
| `explore_exploit.ranking_weight` | `0.10` | Keep a ready starting weight so the feature can be turned on later. |
| `explore_exploit.exploration_rate` | `1.0` | Use a neutral starting exploration constant. |
| `slate_diversity.enabled` | `true` | Stop the final slate from filling with near-identical destinations. |
| `slate_diversity.diversity_lambda` | `0.65` | Lean toward relevance, but still protect variety. |
| `slate_diversity.score_window` | `0.30` | Only diversify candidates that are close enough to the top score. |
| `slate_diversity.similarity_cap` | `0.90` | Treat very similar destinations as redundant. |

### link_freshness

| Key | Seeded value | Why this value |
| --- | --- | --- |
| `link_freshness.ranking_weight` | `0.05` | Give freshness a small boost that is safe for evergreen forum content. |
| `link_freshness.recent_window_days` | `30` | One month is a simple, balanced lookback window. |
| `link_freshness.newest_peer_percent` | `0.25` | Use the freshest quarter of peers for comparison. |
| `link_freshness.min_peer_count` | `3` | Wait for a little history before scoring freshness. |
| `link_freshness.w_recent` | `0.35` | Reward destinations that gained links very recently. |
| `link_freshness.w_growth` | `0.35` | Give equal weight to actual growth speed. |
| `link_freshness.w_cohort` | `0.20` | Use cohort comparison as supporting evidence. |
| `link_freshness.w_loss` | `0.10` | Penalize link loss lightly instead of harshly. |

### anchor

| Key | Seeded value | Why this value |
| --- | --- | --- |
| `phrase_matching.ranking_weight` | `0.08` | Give matching anchor phrases real influence without making them absolute. |
| `phrase_matching.enable_anchor_expansion` | `true` | Let the system discover useful anchor phrases from page text. |
| `phrase_matching.enable_partial_matching` | `true` | Allow near matches so small wording differences do not kill good suggestions. |
| `phrase_matching.context_window_tokens` | `8` | Use enough nearby words to judge context without getting too noisy. |
| `learned_anchor.ranking_weight` | `0.05` | Start small until more live anchor patterns exist. |
| `learned_anchor.minimum_anchor_sources` | `2` | Require at least two sources before trusting a learned pattern. |
| `learned_anchor.minimum_family_support_share` | `0.15` | Ask for some family-level agreement, but not too much. |
| `learned_anchor.enable_noise_filter` | `true` | Filter generic anchors like `click here` and similar noise. |

### clustering

| Key | Seeded value | Why this value |
| --- | --- | --- |
| `clustering.enabled` | `true` | Keep near-duplicate suppression on all the time to prevent spammy slates. |
| `clustering.similarity_threshold` | `0.04` | Use a strict near-duplicate cutoff. |
| `clustering.suppression_penalty` | `20.0` | Push non-canonical duplicates far enough down that they do not crowd the top results. |

### silo

| Key | Seeded value | Why this value |
| --- | --- | --- |
| `silo.mode` | `disabled` | Safe default: do not enforce silos until the taxonomy is really configured. |
| `silo.same_silo_boost` | `0.05` | Keep a gentle same-silo bonus ready for when silo mode is enabled. |
| `silo.cross_silo_penalty` | `0.05` | Keep a gentle cross-silo penalty ready for when silo mode is enabled. |

### other

Phase 17 does not define any extra preset keys outside the groups above.

## Using the Presets Card

### Load a preset

Click `Load` on the preset you want. The UI shows a confirm dialog because loading a preset overwrites all current live in-scope weights.

If you confirm, the backend applies the preset all at once and then writes a history row with `source=preset_applied`.

### Save the current live weights as a new user preset

Click `Save current as new preset`, type a name, and click `Save`.

Important: this saves the live persisted values from the backend, not unsaved edits that are still sitting in a form field on the page. If you changed a signal card but did not click that card's normal `Save` button yet, those unsaved edits are not part of the new preset.

### Rename a user preset

Click the pencil icon on a user preset, type the new name, then press `Enter` or click the check icon.

Only the name changes. The stored weight values do not change.

### Delete a user preset

Click the trash icon, then confirm.

Deleting a preset does not change the live weights. It only removes that saved snapshot.

### Why system presets have a lock icon

The lock icon means `is_system=true`.

System presets come from code and are meant to be stable reference points. The UI hides rename and delete actions for them, and the backend also blocks update and delete requests with `403`.

## Using the Weight History Card

### What each row shows

Each row shows:

- the date and time the change was recorded
- the human source label
- the preset name when the change came from a preset load
- the plain-English reason
- the per-key delta for keys that actually changed

Rows are shown newest first.

Each delta line is the key plus `old -> new`. Keys that did not change are not shown.

### How rollback works

Click `Rollback` on the row you want to undo, then confirm.

Rollback applies that row's `previous_weights` snapshot all at once. In plain English, it restores the state that existed right before that row happened.

Example: if a row says `Preset: Recommended applied by admin`, rolling back that row restores the weights from before `Recommended` was loaded. It does not reapply the row's `new_weights`.

### What rollback writes to history

Rollback does not erase old history.

Instead, rollback creates a brand-new history row with:

- `source=manual`
- `reason=Rollback to YYYY-MM-DD HH:MM UTC`

That new row is the audit trail for the rollback itself.

## Source Labels Explained

| Source label | What it means |
| --- | --- |
| `preset_applied` | A user clicked `Load` on a preset. |
| `manual` | A rollback happened, or a future direct manual edit writes a history row. |
| `r_auto` | The scheduled R auto-tune task changed weights. |

## R Auto-Tune

Phase 17 wires the task, the UI button, the threshold check, the safe apply path, and history logging.

The actual analytics step is still a stub in Phase 17. Right now the task returns no candidate weights, so it is a no-op until FR-018 fills that part in.

### How to trigger it manually

Use the `Run R auto-tune now` button on the `Weight Adjustment History` card.

That button queues a Celery job in the background. It does not wait for the job to finish on the page.

### Change threshold

The task only applies keys whose absolute change is greater than `0.02`.

If a key moves by `0.02` or less, that key is ignored.

### Schedule

The request text says first Monday, but the checked-in Phase 17 code is currently:

`crontab(hour=2, minute=0, day_of_week=0, day_of_month='1-7')`

That is the first Sunday of each month at `02:00 UTC`.

Example: in April 2026, that schedule fires on `2026-04-05 02:00 UTC`.

### History behavior

When the task does apply changes, it writes a history row with `source=r_auto` and stores the Celery task id in `r_run_id`.

## Data Retention Policy

The nightly data retention task runs every day at `03:00 UTC`.

| Model | Retention |
| --- | --- |
| `SearchMetric` | Purged after 12 months. |
| `PipelineRun` | Purged after 90 days. |
| `ImpactReport` | Never purged. |
| `Suggestion` | Never purged. |
| `WeightAdjustmentHistory` | Never purged. |

## Operator Runbook

- After about 30 days of GA4/GSC data, raise `ga4_gsc.ranking_weight` to `0.10`. Small code note: Phase 17 does not have a `ga4_gsc.enabled` key. GA4/GSC is effectively off when the weight is `0.00`.
- After about 500 feedback clicks, set `explore_exploit.enabled=true` and `explore_exploit.exploration_rate=1.414`. Small code note: the live key is `explore_exploit.exploration_rate`; there is no `explore_exploit.ucb1_c` key in Phase 17.
- After silo taxonomy is fully configured, move `silo.mode` from `disabled` to `prefer_same_silo` for a soft start, or to `strict_same_silo` for hard blocking. Then tune `silo.same_silo_boost` and `silo.cross_silo_penalty`.
- After anchor analysis, tune the live anchor controls that exist today: `phrase_matching.ranking_weight`, `phrase_matching.enable_partial_matching`, `phrase_matching.context_window_tokens`, `learned_anchor.ranking_weight`, `learned_anchor.minimum_anchor_sources`, and `learned_anchor.minimum_family_support_share`. Small code note: Phase 17 does not have `anchor.exact_match_boost` or `anchor.partial_match_boost`.
- Save a named user preset before every experiment. That gives you a fast rollback point and a clean comparison point.

## Schema Versioning Note

Old presets stay safe when new signals are added.

If a future phase adds a new key and an older preset JSON does not contain it, `apply_weights()` silently fills the missing key from `PRESET_DEFAULTS`.

That means old presets still load without breaking. The trade-off is simple: the missing new key uses the code fallback until you save a newer preset that includes it explicitly.
