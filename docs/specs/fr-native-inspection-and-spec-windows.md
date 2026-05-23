# FR — Native Inspection Window + Settled-Spec Window (Phase K.3)

[SPEC FRESHNESS: reviewed_at=2026-05-23 next_review=2026-06-23]
[SPEC CITED: feature=native-inspection-window kind=academic_paper id=Brooks1995 verified_at=2026-05-23]
[SPEC CITED: feature=settled-spec-window kind=academic_paper id=Cockburn2001 verified_at=2026-05-23]
[SPEC CITED: feature=both-windows kind=technical_doc id=Pyroscope-OTEL-docs verified_at=2026-05-23]

## Why these two windows exist

The Sticky #1 Spec-Driven Gradual Rewrite Policy gives every newly-merged
native-language artifact (Haskell service, Rust crate, Go sidecar, C++
pybind11 extension) **seven calendar days of open inspection** where any
agent may revisit the design, the implementation, the contract, the
benchmark numbers, the failure modes, and the operator-facing
diagnostics. Once those seven days elapse without a sustained Pyroscope
or OpenTelemetry regression, the artifact **settles** and is closed to
casual edits. Reopening the window requires a documented trigger.

The Sticky also gives every newly-landed source-backed spec under
`docs/specs/` **fourteen calendar days of open authoring** where any
agent may amend the spec freely. After fourteen days the spec is
**settled** and is closed to casual edits. Reopening requires a fresh
citation, measurable KPI drift, or an explicit user request.

Both windows exist to stop **post-merge churn**. Brooks 1995 (*The
Mythical Man-Month*, ISBN 978-0201835953, Chapter 8 — "Calling the
Shot") documents the irreversibility cost of small follow-up edits that
each look harmless but together compound into a multi-week rewrite.
Cockburn 2001 (*Agile Software Development*, ISBN 978-0201699692,
Chapter 6 — "Cooperating, Coordinating, Reflecting") names this the
"protection window" pattern in incremental delivery: each delivery is
fenced for a fixed period so the team can observe its real-world
behavior before the next round of edits. The Pyroscope and OpenTelemetry
official docs (https://pyroscope.io/docs/, https://opentelemetry.io/docs/)
provide the regression evidence path that reopens a native artifact's
window when its profile drifts measurably for ten consecutive minutes.

## Native Inspection Window — seven days, reopened by regression or user request

**Scope:** every file matching one of:

- `services/<name>/**` (Haskell, Rust, Go sidecar source trees)
- `backend/extensions/**` (C++ pybind11 extensions)
- any file with extension `.rs`, `.cpp`, `.hpp`, `.hs`, `.go`

**Lifecycle marker:** each merge of a native artifact carries
`[NATIVE INSPECTION WINDOW: file=<repo-relative-path> opened_at=<ISO8601>
closes_at=<opened_at + 7 days>]` in the AGENT-HANDOFF.md entry for that
merge commit.

**During the open window:** any agent may edit the artifact freely,
update its tests, change its contract, retune its benchmarks. No
additional evidence required.

**After the window closes (settled state):** edits to the artifact are
hard-blocked at commit time by `.githooks/check-native-inspection-window.py`
UNLESS the AGENT-HANDOFF entry carries one of three reopen markers:

1. `[USER REQUEST INSPECTION: file=<path> reason="<≥ 20-char plain-English>"]`
   — the user explicitly asked for a second pass.
2. `[PYROSCOPE REGRESSION: file=<path> baseline_p95_ms=<X> observed_p95_ms=<Y>
   sustained_minutes=<N>]` with `sustained_minutes >= 10` and Y at least 1.5×
   X — measurable performance regression.
3. `[OTEL_PROFILE REGRESSION: file=<path> baseline_p95_ms=<X> observed_p95_ms=<Y>
   sustained_minutes=<N>]` with the same numeric threshold.

The hook resolves the artifact's `closes_at` by scanning AGENT-HANDOFF
back-to-front for the most recent `NATIVE INSPECTION WINDOW` marker
mentioning the staged path. Files with no prior window are treated as
"not yet merged" and pass freely.

## Settled-Spec Window — fourteen days, reopened by citation drift, KPI drift, or user request

**Scope:** every file matching `docs/specs/*.md`.

**Lifecycle marker:** each spec landing carries the existing
`[SPEC PROOF: specs=<paths> ... checked_at=<YYYY-MM-DD> status=current]`
which doubles as the window opener. `opened_at` for the spec is
`checked_at` plus 23:59:59Z. `closes_at` is `opened_at + 14 days`.

**During the open window:** any agent may amend the spec freely (the
existing `check-spec-citation` hook already enforces citation freshness
and source-backed evidence).

**After the window closes (settled state):** edits to the spec are
hard-blocked at commit time by `.githooks/check-spec-window.py` UNLESS
the AGENT-HANDOFF entry carries one of three reopen markers:

1. `[USER REQUEST SPEC EDIT: spec=<path> reason="<≥ 20-char plain-English>"]`
2. `[SPEC CITATION DRIFT: spec=<path> previous_id=<id> new_id=<id>
   evidence_url=<URL>]` — a newer authoritative source supersedes the
   original citation.
3. `[SPEC KPI DRIFT: spec=<path> metric=<name> baseline=<X> observed=<Y>
   threshold_pct=<P>]` — the operational KPI the spec cites has drifted
   past `threshold_pct` and the spec no longer matches reality.

## Implementation summary (this commit)

- `.githooks/check-native-inspection-window.py` — fires on every commit
  touching a native-language path. Refuses post-window edits without a
  documented reopen marker.
- `.githooks/check-spec-window.py` — fires on every commit touching
  `docs/specs/*.md`. Refuses post-window edits without a documented
  reopen marker.
- `.githooks/test_check_native_inspection_window.py` — paired test suite
  covering open-window passes, post-window blocks, and each of the three
  reopen markers.
- `.githooks/test_check_spec_window.py` — paired test suite with the
  equivalent scenarios for spec edits.
- `scripts/precommit-docker.sh` wires both hooks after
  `check-rewrite-quota` and before `check-autoissue-quota`.

The hooks are intentionally small (under 250 lines each) and follow the
shape of `.githooks/check-sticky-1-read.py` so future agents find the
pattern. Both hooks share `_CODE_PREFIXES`, `_staged_code_files`, and
`_staged_handoff_diff` helpers that the K.3 commit extracts from
`check-sticky-1-read.py` and `check-rewrite-quota.py` into
`.githooks/_hook_helpers.py` (DRY refactor).

## Source citations

- Brooks 1995, *The Mythical Man-Month* (Anniversary Edition),
  ISBN 978-0201835953, Chapter 8 "Calling the Shot" — irreversibility cost.
- Cockburn 2001, *Agile Software Development: The Cooperative Game*,
  ISBN 978-0201699692, Chapter 6 — protection window pattern.
- Pyroscope official docs, https://pyroscope.io/docs/ — continuous-profiling
  regression evidence.
- OpenTelemetry official docs, https://opentelemetry.io/docs/ — OTLP
  profile signal regression evidence.
- The companion Sticky #1 body filed at paper_trail row 11
  (SHA prefix 7b8d04510bf49e49) names the two windows in its addendum
  sections "Native Inspection Window" and "Settled-Spec Window".
