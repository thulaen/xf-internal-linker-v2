# AUTOTUNER-FUTURE-AWARENESS.md — One-Rule Brief

**Status:** PARAMOUNT. Every AI agent reads this before adding any new ranking weight, meta-algorithm parameter, or signal.

## The rule

**Every new ranking weight or meta-algorithm parameter MUST land in the autotuner's tunable registry AND the Recommended preset within the same commit it's first introduced. Default ON. Sensible starting value with a citation.**

Three things, one commit, no exceptions:

1. **Tunable registry entry.** The autotuner reads from a single registry file at [`backend/apps/suggestions/tunable_registry.py`](../backend/apps/suggestions/tunable_registry.py). Every new weight goes into `BLEND_WEIGHTS`; every new meta-algo parameter goes into `META_PARAMS`. The schema is `key → (lower_bound, upper_bound, citation, default)`. The autotuner [`backend/apps/suggestions/services/meta_tuner.py`](../backend/apps/suggestions/services/meta_tuner.py) and [`backend/apps/suggestions/services/weight_tuner.py`](../backend/apps/suggestions/services/weight_tuner.py) read from this registry, so adding the entry is the entire wiring.

2. **Recommended preset migration.** A data migration in the same commit upserts the new key into `RECOMMENDED_PRESET_WEIGHTS` at [`backend/apps/suggestions/recommended_weights.py`](../backend/apps/suggestions/recommended_weights.py) AND into the `WeightPreset` row where `is_system=True AND name='Recommended'`. Without this, existing installs never see the new defaults when they load the preset.

3. **Default ON, non-zero, non-`false`.** Per [`DEFAULT-ON-RULE.md`](../DEFAULT-ON-RULE.md). Seed an `AppSetting` row in a migration that uses `get_or_create` (NOT `update_or_create`). The value must be a sensible starting point — not 0, not `false`, not `off`. Pre-commit hook [`.githooks/check-default-on-rule.py`](../.githooks/check-default-on-rule.py) blocks migrations that violate this.

## What this gets you

- The autotuner automatically picks up any new weight on its next run — no code change required.
- Existing installs see the new defaults the next time they load the Recommended preset.
- The autotuner cannot zero out the new feature: every registry entry has a positive lower bound.
- The user never has to think "did I remember to wire that up everywhere" — the registry is the single source of truth.

## What enforces this

Two pre-commit hooks:

- [`.githooks/check-autotuner-registry.py`](../.githooks/check-autotuner-registry.py) — when a migration adds a tunable `AppSetting.key` matching a known prefix (`pipeline.`, `slate_diversity.`, `click_distance.`, `explore_exploit.`, `field_aware_relevance.`, `clustering.`, `score_`, `w_`), the hook checks the same commit for either: (a) a new entry in `tunable_registry.py`, OR (b) an explicit `# AUTOTUNER-EXCLUDED: <reason>` comment in the migration. Without one of those, the commit fails.
- [`.githooks/check-recommended-preset-coverage.py`](../.githooks/check-recommended-preset-coverage.py) — when the same migration adds a tunable key, the hook also checks for either an upsert into `WeightPreset.objects.filter(name='Recommended', is_system=True)` OR an append to `RECOMMENDED_PRESET_WEIGHTS` in `recommended_weights.py`. Without that, the commit fails.

## How to satisfy the rule (canonical example)

For a new weight `score_freshness_decay`:

```python
# backend/apps/suggestions/tunable_registry.py
BLEND_WEIGHTS["w_freshness_decay"] = TunableWeight(
    lower=0.01,                    # never zero (DEFAULT-ON-RULE.md)
    upper=0.30,                    # bound at 30% blend share
    default=0.08,                  # sensible starting point
    citation="Lavrenko & Croft 2001 (relevance models with time decay)",
)

# backend/apps/suggestions/recommended_weights.py
RECOMMENDED_PRESET_WEIGHTS["w_freshness_decay"] = "0.08"

# backend/apps/suggestions/migrations/0NNN_add_freshness_decay.py
def forwards(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.get_or_create(
        key="ranking.w_freshness_decay",
        defaults={"value": "0.08"},
    )
    # Recommended preset upsert
    WeightPreset = apps.get_model("suggestions", "WeightPreset")
    preset = WeightPreset.objects.filter(
        name="Recommended", is_system=True
    ).first()
    if preset:
        preset.weights["w_freshness_decay"] = "0.08"
        preset.save(update_fields=["weights"])
```

That's it. The autotuner will start tuning the new weight on its next monthly run. Existing installs see the new default the next time the preset is applied. New installs get it baked in via `get_or_create`.

## When the rule does NOT apply

Some keys live in the Recommended preset for context but aren't safe to auto-tune (e.g. data-driven decay constants that depend on actual ingest cadence). For those:

- Skip the registry step.
- Add a `# AUTOTUNER-EXCLUDED: <reason>` comment in the migration that introduces the key.
- The hook recognises the comment and lets the commit through.
- The key is still in the Recommended preset (so existing installs see the default) — it just isn't pickable by the autotuner.

Example: `pipeline.embedding_age_half_life_days` is excluded because moving it ±5% per month would damage the freshness signal in unpredictable ways.

## Why this rule exists

Before 2026-05-09, adding a new weight required editing four places: the `AppSetting` migration, `recommended_weights.py`, `meta_tuner.py` (or `weight_tuner.py`), and the spec. Three of those were easy to forget. When forgotten:

- The autotuner ignored the new weight forever (silent under-tuning).
- Existing installs never saw the new default unless an operator manually applied the Recommended preset.
- New installs got an untuned default that drifted further from what the autotuner would have chosen.

The single registry + paired migration + two hooks pattern collapses four edits into two and makes silent skipping impossible.

## Related rules

- [`DEFAULT-ON-RULE.md`](../DEFAULT-ON-RULE.md) — defaults are always ON with a non-zero starting value.
- [`CITATION-RULE.md`](../CITATION-RULE.md) — every default needs a citation in `docs/specs/<id>.md`.
- [`docs/RANKING-GATES.md`](RANKING-GATES.md) Gate A11 — checkpoint that a new weight is registered before code lands.
- [`NO-DUPLICATES.md`](../NO-DUPLICATES.md) — if the new weight is per-content (e.g. cached score), the artefact table must satisfy the no-duplicates invariant too.
