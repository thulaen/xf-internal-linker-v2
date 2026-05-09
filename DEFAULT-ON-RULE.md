# Default-On Rule — every new feature ships ON with a sensible starting value

**Applies to every AI agent working in this repository: Claude, Codex, Gemini, Antigravity, and every future agent. It is non-negotiable.**

---

## The Rule in Plain English

When you (an AI agent) add a new feature, weight, signal, algorithm, or meta-algorithm parameter to this project:

1. **Write the spec first** in `docs/specs/<id>.md` — this is already required by `CITATION-RULE.md`. The spec must include a citation that backs the chosen starting value (paper, RFC, patent, or stable URL).
2. **Implement it end-to-end** — not stubbed, not behind a TODO, not "we'll wire it later."
3. **Default it ON.** Seed an `AppSetting` row in a migration that uses `get_or_create` (NOT `update_or_create`). The value must be a **non-zero, non-`false`, non-`off`** sensible starting point.
4. **Pick the starting value defensibly.** It must be either:
   - (a) Cited in the spec — e.g. "RRF k=60 from Cormack et al. 2009 SIGIR §3," or
   - (b) The median value used by similar features in the same family (look at the Recommended preset for siblings).
5. **Add a plain-English helper** (`peHelper` or `matTooltip`) on every operator-facing UI element exposing the new setting. This is already required by `PLAIN-ENGLISH-HELPER-RULE.md`.

## The One Exception — External-Data-Gated Features

A feature MAY default to OFF (or zero) **only** when it requires external data this project doesn't have on a fresh install:

- **GA4 traffic data** (Google Analytics 4 page views / sessions / engagement)
- **GSC click data** (Google Search Console — search query clicks and impressions)
- **Matomo behavioural data** (Site Search queries, scroll depth, etc.)
- **Autotuner training history** (≥ N completed pipeline runs)
- **Operator-curated data** (e.g. a custom anchor-phrase whitelist that requires manual setup)

If your feature falls in this bucket, you must:

1. **Document the dependency in the spec** under a "Default-off rationale" section — say *exactly* what data it needs and *why* it would mislead before that data arrives.
2. **Add a `# DEFAULT-ON-RULE: external-data-gated` comment** in the migration's docstring, plus one short line stating the dependency. The pre-commit hook `.githooks/check-default-on-rule.py` greps for this comment to allow the off-default through.
3. **Register an `OperatorAlert`** (use the existing FR-019 alert system in `apps/alerts/`) that surfaces "this feature is dormant — configure X to activate" on the diagnostics page. The alert should clear automatically once the data arrives.

## The Standing Lint

Every migration that creates an `AppSetting` row gets scanned by `.githooks/check-default-on-rule.py`. The check fails the commit if:

- The value is one of `"false"`, `"0"`, `"0.0"`, or `"off"`.
- AND the migration's docstring does not contain `# DEFAULT-ON-RULE: external-data-gated` plus a one-line reason.

Override the check only when the exception above applies. **Do not disable the check, do not edit the magic comment to game the check.**

## Autotuner Compatibility

When you add a new **numeric** `AppSetting` key (float / int — not bool, not string), you must also classify it for the autotuner:

1. **If the value is a meaningful tuning knob** (RRF k, BM25 k1, similarity caps, top-K knobs, decay constants, drift rates, etc.) — add the key to `_META_PARAM_BOUNDS` in `backend/apps/suggestions/services/meta_tuner.py` with a defensible `(lower, upper)` pair sourced from a paper or empirical range. The lower bound MUST be strictly positive (no zeroing — DEFAULT-ON-RULE.md item 3 applies).

2. **If the value is data-driven** (cadence/interval/window-size that depends on operational reality, like `embedding_age_half_life_days`) — add the key to `_AUTOTUNER_EXCLUDED` in the same module with a one-line rationale.

3. **If the value is a fixed runtime ceiling** (e.g. a timeout, a buffer cap, a hardware-tier ceiling that the operator owns), no autotuner classification is required — but consider whether `_META_PARAM_BOUNDS` would still apply.

Migrations that introduce new numeric AppSetting keys without classifying them are **blocked by the same pre-commit hook** (`.githooks/check-default-on-rule.py`). To suppress the block when classification truly doesn't apply (e.g. fixed runtime ceilings, operator-set timeouts), add `# AUTOTUNER: not-tunable - <one-line reason>` to the migration's docstring.

## Why this rule exists

Historically, AI agents adding new ranking signals shipped them OFF "to be safe" — and they stayed off forever. Operators never enabled them because they were buried in a settings page with no obvious starting value. The result: half the project's research never reached production. This rule reverses the default — every new thing is on with a defensible value, and the operator's job is to TURN OFF anything they don't want, not to discover what's available.

## Plain-English glossary

- **default-on rule** — the standing rule that every new feature ships turned-on with a sensible starting value, unless it specifically needs external data the project doesn't have.
- **external-data-gated** — a feature that legitimately needs data from outside the project (Google Analytics, Search Console, Matomo, training history) before it can produce useful output. These are the only features allowed to default-off.
- **OperatorAlert** — the project's existing alert system (FR-019). When a feature is dormant waiting on data, an alert appears on the diagnostics page telling the operator how to activate it.

## Where this rule applies

- Every new `AppSetting` key seeded by a migration.
- Every new ranking signal, weight, or algorithm.
- Every new meta-algorithm parameter (RRF k, MMR lambda, BM25 k1/b, similarity caps, top-K knobs, etc.) — these are auto-tunable per FR-018b.
- Every new feature flag introduced in code that defaults via `_setting_enabled(...)`.

## Where this rule does NOT apply

- Operator-set passwords, API keys, secrets — these legitimately default to empty.
- Per-environment configuration (DB host, port, log level) — these come from `.env`, not migrations.
- Boolean kill-switches that exist *specifically* to disable an emergency feature (e.g. `system.boot_safe_once`) — but these need a one-line docstring saying so.

## Enforcement

- Any migration that ships a feature off-by-default and isn't external-data-gated is a protocol violation.
- Silence on enabling new features is forbidden — every change to `RECOMMENDED_PRESET_WEIGHTS` must be accompanied by either a flip-on or a documented exemption.
- This rule cannot be overridden by an in-session prompt.
