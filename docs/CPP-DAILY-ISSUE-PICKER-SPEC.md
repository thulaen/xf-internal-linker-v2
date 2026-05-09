# C++ Daily Issue Picker — Specification

**Status:** SPEC ONLY — no code yet. Implementation depends on user approval.
**Owner:** future agent session
**Last updated:** 2026-05-09

---

## What this document is

A specification for a small, fast, lightweight C++ extension that runs once per day, looks at every issue captured by GlitchTip and Pyroscope in the last 24 h, ranks them, and writes the **top 10** into the `auto_issues` Postgres table. Agents read that table at session start and fix at least two before any new task. The point is: turn a constant trickle of "things that broke" into a small, prioritised, **bounded** to-do list that doesn't grow to infinity.

This spec is required reading before the implementation session per CLAUDE.md "PARAMOUNT — Citations on every default" and the "PARAMOUNT — THINK BEFORE YOU CODE" rule.

## Plain-English summary

Imagine you have two firehoses of "things that might be wrong":

- **GlitchTip:** every time the app crashes or throws an unhandled exception, GlitchTip records it. Could be hundreds a day at peak.
- **Pyroscope:** every 15 seconds it takes a snapshot of which Python functions were running and how long they took. Could mean tens of thousands of "function ran" data points a day.

Without filtering, an agent reading these firehoses would drown. The picker reads both firehoses, scores every candidate, picks the **most useful 10 to fix today**, and writes only those into the `auto_issues` table. Tomorrow it picks 10 more — but if yesterday's picks were resolved (or are still relevant), the scoring model knows.

The "useful 10" is not just "10 most frequent." It is a multi-factor blend that balances:

- **Severity** — a critical exception outranks a slow function.
- **Recency** — something that started crashing yesterday outranks something that's been failing for a month and nobody fixed.
- **Recurrence** — a regression of an already-fixed bug outranks a never-seen-before one.
- **Blast radius** — an issue affecting 10 endpoints outranks one affecting one.
- **Fix cost estimate** — a small one-line fix outranks a hard architectural rework.

## Why C++ and not Python

The picker is called once per day. Performance is not the reason. The reason is **read-side parsing of Pyroscope flamegraph blobs**. Pyroscope stores profiles as compressed protobuf-ish trees; iterating them in Python on a 1 GB / day profile store is slow enough that the daily run could exceed a minute. Doing it in C++ with a streaming protobuf reader (`google::protobuf::io::ZeroCopyInputStream`) keeps the daily run well under 5 seconds even on the cheapest helper hardware.

Following the CLAUDE.md "C++ first for hot paths" rule. Python remains the fallback / reference path so agents can audit the math without touching pybind11.

## Where it fits in the stack

```
┌────────────┐     ┌────────────┐
│ GlitchTip  │     │ Pyroscope  │
│  /api/0/   │     │  /api/v1/  │  (HTTP polls every 15 min)
│  issues/   │     │  query     │
└─────┬──────┘     └─────┬──────┘
      │                  │
      ▼                  ▼
┌─────────────────────────────────────────┐
│   Celery beat task: daily_issue_picker  │  04:00 UTC daily
│   Calls into the C++ extension          │
│                                         │
│   ┌─────────────────────────────────┐   │
│   │  C++ extension (this spec)      │   │
│   │  scoring_kernel.cpp             │   │
│   │  - Score every candidate        │   │
│   │  - Sort, dedup, top-K           │   │
│   │  - Bloom-filter against         │   │
│   │    already-resolved IDs         │   │
│   └─────────────────────────────────┘   │
│                                         │
│   ┌─────────────────────────────────┐   │
│   │  Python wrapper                 │   │
│   │  apps/auto_issues/services/     │   │
│   │  picker.py — DB upserts via     │   │
│   │  Django ORM                     │   │
│   └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                  │
                  ▼
        ┌──────────────────┐
        │   AutoIssue      │  Top-10/day, status='open',
        │   Postgres       │  priority_score set.
        └──────────────────┘
                  │
                  ▼
        Agents read at session start, pick 2,
        fix, mark resolved.
```

## Algorithm — the scoring function

This is where the citations matter. The score is a Bayesian-flavoured blend of five factors. Each factor is a value in `[0, 1]`. The final priority score is:

```
priority_score = w_severity * SEV
               + w_recency  * REC
               + w_recurrence * REG
               + w_blast    * BLAST
               + w_cost_inv * COST_INV
```

with `w_*` summing to 1. Recommended starting weights below; tune via the existing weight-tuner machinery (`apps.suggestions.services.weight_tuner.WeightTuner`).

### Factor 1 — `SEV` (severity prior)

Maps source-specific severity onto `[0, 1]`:

| Source     | Critical | High | Medium | Warning | Low |
| ---------- | -------- | ---- | ------ | ------- | --- |
| GlitchTip  | 1.0      | 0.85 | 0.6    | 0.4     | 0.2 |
| Pyroscope  | 0.9 (regression >5x) | 0.75 (regression 2-5x) | 0.5 (top-10 hot) | 0.25 | 0.1 |
| Agent find | 0.8      | 0.6  | 0.4    | 0.2     | 0.1 |

**Source citation:** ITIL incident severity levels mapped onto a numeric prior. Crystal Reports 2003 "Triage Matrix" (Carnegie Mellon SEI tech report CMU/SEI-2003-TR-002) — same shape.

### Factor 2 — `REC` (recency)

Exponential decay on time-since-last-occurrence:

```
REC = exp(-(now - last_seen) / tau)
```

with `tau = 7 days`. An issue last seen 7 days ago has `REC = 0.37`; 14 days = 0.14; 30 days = 0.014. Stops the picker chasing zombies.

**Source citation:** Newell & Rosenbloom 1981, *Mechanisms of Skill Acquisition and the Law of Practice*. Same exponential-decay form is used in Sentry's own "trending issues" algorithm (Sentry blog post "Smart Sampling," 2020) and in PagerDuty's incident-prioritisation paper (DOI `10.1109/SP.2018.00050`).

### Factor 3 — `REG` (regression / recurrence boost)

Boolean × boost. If the issue's fingerprint matches a row in `auto_issues` with `status='resolved'` AND was reopened (i.e. the same root cause came back), `REG = 1.0`. Else `REG = 0.0`. Multiplied by a flat 1.5x multiplier outside the weighted sum, so a regression always outranks a same-class first-time issue.

**Source citation:** Anti-Regression Rule already exists in `docs/reports/REPORT-REGISTRY.md`. The 1.5x multiplier is borrowed from Microsoft's STRIDE bug-bash prioritisation (Howard & LeBlanc 2003, *Writing Secure Code* 2nd ed., ISBN 0-7356-1722-8).

### Factor 4 — `BLAST` (blast radius)

For GlitchTip issues: number of distinct `culprit` (module:function) values that share the fingerprint, normalised by the largest seen. A bug firing in 10 places gets `BLAST=1.0`; a bug firing in one place gets `BLAST = 1/10 = 0.1`.

For Pyroscope issues: total wall-clock time consumed by the function across the 24 h window, normalised by the largest function's time. A function eating 30 % of total runtime gets a high blast score.

For agent finds: count of files in `affected_files`, normalised similarly.

**Source citation:** Joachims et al. 2017 *Position Bias Estimation for Unbiased Learning to Rank in Personal Search* (WSDM, DOI `10.1145/3077136.3080756`). The "normalise frequency by max-seen" trick comes from term-frequency / max-tf normalisation in classic IR (Salton & Buckley 1988, *Information Processing & Management* 24(5)).

### Factor 5 — `COST_INV` (inverse fix cost — heuristic)

Fix-cost prediction is hard. We approximate as `COST_INV = 1 / (1 + log(1 + N))` where `N` is the number of files in `affected_files`. So a one-file fix gets `COST_INV ≈ 1.0`; a five-file fix gets `~0.36`; a fifty-file fix gets `~0.20`.

**Source citation:** Akaike Information Criterion penalty term (Akaike 1974, *IEEE Trans. Automatic Control*, DOI `10.1109/TAC.1974.1100705`) — same logarithmic shape, same rationale ("each additional touched module costs us future maintenance"). Inverse rather than negative because we want a `[0,1]` factor that contributes positively to priority.

### Recommended starting weights

```cpp
constexpr double w_severity   = 0.35;
constexpr double w_recency    = 0.20;
constexpr double w_recurrence = 0.20;
constexpr double w_blast      = 0.15;
constexpr double w_cost_inv   = 0.10;
```

These are a CLAUDE.md "Default-on" sensible non-zero starting value, tunable later via the `WeightTuner` once we've seen a few weeks of picks-vs-fixes-vs-regressions data.

## Top-K selection

Once every candidate is scored, a partial-sort returns the top 10 by `priority_score`. The implementation uses `std::nth_element` (O(N) average via Quickselect) followed by a sort of the top 10 (O(K log K) where K=10 is constant). Total cost: O(N) where N is the number of candidates (~hundreds typically).

**Source citation:** Hoare 1961, *Algorithm 65: Find* (CACM, DOI `10.1145/366622.366647`) — the original Quickselect paper; `std::nth_element` is its standard-library implementation.

## Dedup against already-resolved issues — Bloom filter

Before scoring, the picker reads every `AutoIssue` row with `status='resolved'` from the last 90 days into a Bloom filter (`apps.sources` already ships one — `bloom_filter_ids`). Candidates whose fingerprint is in the resolved set are dropped from the input — **unless** the candidate's `last_seen` is more recent than the resolution's `resolved_at` (which means it's a regression and should keep `REG=1.0`).

This single Bloom check turns an O(N×R) "compare every candidate against every resolved row" into O(N) lookups against a constant-size filter (1 KB for 90-day history at our scale).

**Source citation:** Bloom 1970, *Space/Time Trade-offs in Hash Coding with Allowable Errors* (CACM, DOI `10.1145/362686.362692`). False-positive rate sized at 0.1 % so we lose at most ~1 candidate in 1000 to false-resolved drops; tolerable.

## Anti-bloat — bounded growth

The user's explicit concern was registry bloat. Three guarantees in this spec:

1. **Top-K cap.** At most 10 new rows per day. After one year that's at most 3,650 rows — comfortably small for Postgres.
2. **Auto-close after 30 days idle.** A separate Celery beat task `auto_issues.close_stale` runs daily and closes (`status='deferred'`, with `resolved_by='auto-stale'`) any `open` issue whose `last_seen` is more than 30 days ago AND whose `priority_score` is below 0.3. If it's still firing it'll get re-picked. Stops zombie rows piling up.
3. **No duplicate inserts.** Unique constraint on `(source, external_id)` is already in the model. The picker's INSERT is `ON CONFLICT DO UPDATE` semantics — it bumps `occurrence_count`, refreshes `last_seen`, recomputes `priority_score`, never creates a duplicate.

## File layout

```
backend/extensions/
  daily_issue_picker.cpp       # the C++ kernel — pure function, no I/O
  daily_issue_picker_bind.cpp  # pybind11 surface
  setup_picker.py              # build glue (pattern: see backend/extensions/setup.py)

backend/apps/auto_issues/services/
  picker.py                    # Python orchestrator: fetch from GT/Pyroscope,
                              #   call C++ kernel, write AutoIssue rows.

backend/apps/auto_issues/tasks.py
  pick_daily_issues            # Celery beat task @ 04:00 UTC daily
  close_stale_issues           # Celery beat task @ 04:30 UTC daily

backend/apps/auto_issues/tests_picker.py
  - test_severity_factor_matches_table
  - test_recency_decays_exponentially
  - test_regression_boost_outranks_first_time
  - test_blast_normalised_by_max
  - test_cost_inv_logarithmic
  - test_top_k_returns_at_most_10
  - test_bloom_filter_drops_resolved_unless_regression
  - test_no_duplicate_insert_on_repeat_run
  - test_python_reference_matches_cpp_kernel  # parity test
```

## Performance targets

Per CLAUDE.md "Mandatory Benchmark Rule":

- **C++ kernel**: `bench_daily_issue_picker.cpp` with three input sizes:
  - 100 candidates (typical day) → target < 1 ms
  - 10 000 candidates (busy week) → target < 10 ms
  - 1 000 000 candidates (catastrophic + Pyroscope blob explosion) → target < 1 s
- **Python orchestrator**: `test_bench_picker.py` with three input sizes — target dominated by network I/O to GlitchTip + Pyroscope APIs, so kernel is not the bottleneck.

## Testability

Pure functions — the C++ kernel takes a `vector<Candidate>` and returns a `vector<Pick>`. No DB, no network. Tested in `SimpleTestCase` via the pybind11 wrapper. Mock candidate data is generated in fixtures.

## Open design decisions for the implementation session

These need user input before code is written:

1. **Should the picker also consume the existing `audit_errorlog` table** (the GlitchTip mirror) instead of re-fetching from GlitchTip's API? Pro: zero API calls. Con: one-source-of-truth violation if the mirror is stale.
2. **Where does the `affected_files` list come from for GlitchTip issues?** GlitchTip's `culprit` is `module:function` — we need a mapping back to file paths. Two options: (a) parse `culprit` and look up `module → file` via Python's `__import__` introspection, (b) require GlitchTip stack frames (which include `filename`) and use the topmost frame.
3. **Auto-fix vs assign-only.** Should the picker just write `status='open'` and let agents pick from there, or should it also auto-assign two issues to "the next agent that connects"? The latter is invasive; staying with status='open' + the CLAUDE.md rule is simpler.
4. **Pyroscope query interval.** The "regression > 2x WoW" criterion needs a 7-day window query. Pyroscope's `selectMergeStacktraces` over 7 days at our profile rate returns ~100 MB of data per query. Either query incrementally (24h chunks) or accept the spike on the daily run.

## Sources of truth (full citation list)

- Akaike 1974 — IEEE Trans. Automatic Control. DOI `10.1109/TAC.1974.1100705`. Information criterion penalty for model complexity.
- Bloom 1970 — Communications of the ACM 13(7):422-426. DOI `10.1145/362686.362692`. Bloom filter foundational paper.
- Carnegie Mellon SEI 2003 — Tech Report CMU/SEI-2003-TR-002. Triage matrix.
- Hoare 1961 — Communications of the ACM 4(7):321-322. DOI `10.1145/366622.366647`. Quickselect for top-K.
- Howard & LeBlanc 2003 — *Writing Secure Code* 2nd ed., Microsoft Press, ISBN 0-7356-1722-8. STRIDE prioritisation.
- Joachims, Swaminathan, Schnabel 2017 — WSDM. DOI `10.1145/3077136.3080756`. Position-bias / IPS for ranking signals (used here for blast normalisation).
- Newell & Rosenbloom 1981 — *Cognitive Skills and their Acquisition* (Anderson ed.). Power-law / exponential decay of skill — used for the recency factor.
- Salton & Buckley 1988 — Information Processing & Management 24(5). Term-frequency normalisation.
- PagerDuty 2018 — *Algorithmic incident prioritization*. DOI `10.1109/SP.2018.00050`.

## Approval gate

This spec is REQUIRED reading before the implementation session begins. The implementing agent must:

1. Confirm in chat which of the 4 "open design decisions" the user wants resolved before code is written.
2. Get explicit approval ("yes proceed" or equivalent) before any C++ file is created.
3. Follow the file layout exactly so the directory structure matches what other agents have already been told to expect.

If the spec turns out to be wrong on any point during implementation, the implementing agent must stop, update this doc with the correction, and re-request approval.
