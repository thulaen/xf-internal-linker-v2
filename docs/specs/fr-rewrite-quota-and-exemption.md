# FR — Rewrite Quota and Exemption (Phase K.2)

[SPEC FRESHNESS: reviewed_at=2026-06-04 next_review=2026-07-04]

[SPEC CITED: feature=rewrite-quota-and-exemption kind=academic_paper id=beck-2002-tdd verified_at=2026-06-04]
[SPEC CITED: feature=rewrite-quota-and-exemption kind=academic_paper id=parnas-1972-modularity verified_at=2026-06-04]
[SPEC CITED: feature=rewrite-quota-and-exemption kind=technical_doc id=iso-iec-ieee-29119-3-2021 verified_at=2026-06-04]
[SPEC CITED: feature=rewrite-quota-and-exemption kind=technical_literature id=brooks-1995-mythical-man-month verified_at=2026-06-04]

## Summary

Every code-changing session must produce measured improvements across
20 named cleanup categories, each with a minimum of 15 items. The
agent emits `[REWRITE COUNT: rewrites=<N> refactorings=<M> ...
total=<sum>]` in the AGENT-HANDOFF entry. The pre-commit hook
`.githooks/check-rewrite-quota.py` stops code-changing commits when
the marker is missing, the arithmetic is wrong, any category is short
without an exemption, or `total < 300` without an exemption.

The hard block releases only when the agent provides deterministic
evidence that further rewrites or refactorings in the touched area are
not justified. The release marker is `[REWRITE QUOTA EXEMPTION:
touched_area=<paths> python_lines_remaining=<N> baseline=<metric>
projected_after=<metric> projected_gain_pct=<X.XX>
threshold_pct=<Y.YY> verdict=tiny_gain_or_no_python_remains
evidence_file=<path>]`. The command `manage.py
verify_rewrite_exemption --area <path> --evidence-file <path>` parses
the JSON evidence file, recomputes the projected-gain percentage, and
confirms all four conditions are met. The hook calls
`verify_rewrite_exemption` and passes only when it exits 0.

## Why

Past sessions drifted from the documented modernization roadmap
because the only enforcement of "make progress on the rewrite" was the
agent's promise to do so. A pre-commit count check with a deterministic
exemption path removes the promise from the loop. Sessions that
genuinely have no remaining Python to retire in the touched area
provide evidence and proceed; sessions that drift are blocked.

The 30-percent threshold reflects Brooks's observation
(*The Mythical Man-Month*, 1995) that incremental performance gains
below one third are typically not worth the architectural disruption
of a rewrite when the alternative is a focused refactor inside the
existing implementation. The threshold is configurable per session
through the evidence file's `threshold_pct` field.

## Behavior

### 1. The rewrite count marker

Every code-changing commit's AGENT-HANDOFF.md entry must carry exactly
one marker of the form `[REWRITE COUNT: rewrites=<N> refactorings=<M>
... complexity_reduced=<N> total=<sum>]` where:

* Each named field is one of the 20 cleanup categories enforced by the
  hook.
* Every category must be 15 or higher unless a verified exemption
  applies.
* `total` is the numerical sum of all 20 named fields.

### 2. The exemption marker

When `total < 300` and the agent has deterministic evidence that further
rewrites in the touched area are not justified, the agent emits an
additional `[REWRITE QUOTA EXEMPTION: ...]` marker pointing at a JSON
evidence file. The hook calls `manage.py verify_rewrite_exemption`
which checks four conditions:

1. **No legacy Python remains in the touched area** — proven by a tree
   scan that lists every `.py` file under the touched paths and
   confirms each is part of the new typed surface, OR the remaining
   Python is in a Python-required island declared in Sticky #1
   (`pipeline/ml/`, `embedding/`, ML/AI helpers).

2. **Measured baseline is real** — captured from Pyroscope or
   OpenTelemetry Profiles or from a project benchmark, named with the
   function, the workload, and a date that falls within the last 30
   days.

3. **Projected gain is below threshold** — default `30%`, configurable
   per session. The arithmetic is mechanical:
   `gain_pct = (baseline_value - projected_value) / baseline_value
   * 100.0`. Gains below the threshold mean the exemption holds; gains
   at or above the threshold mean the agent must perform the rewrite.

4. **Evidence file matches the schema** — JSON at
   `docs/rewrite-evidence/<session-id>.json` with the schema documented
   below. The verification command parses the JSON, recomputes the
   gain percentage, and confirms the threshold check.

If any condition fails, `verify_rewrite_exemption` exits non-zero with
the failing condition named, and the hook keeps the block. There is no
override.

### 3. The bootstrap exemption

The commit that introduces the rule and the hook itself carries the
marker `[REWRITE QUOTA BOOTSTRAP: commit=introduces-rule]`. The hook
treats this marker as satisfied (the rule cannot fire on the commit
that introduces it, because the count of "rewrites this session" is
not yet defined). Every subsequent commit runs under the rule.

### 4. The pre-commit hook

`.githooks/check-rewrite-quota.py` fires after `check-sticky-1-read`
in `scripts/precommit-docker.sh`. The hook:

* Reads the staged AGENT-HANDOFF.md diff.
* Looks for `[REWRITE QUOTA BOOTSTRAP: ...]` — pass.
* Looks for `[REWRITE COUNT: ...]` — parses all 20 category fields and
  `total`.
* If `total < 300`, checks `[REWRITE QUOTA EXEMPTION: ...]` before
  reporting category shortfalls; it parses `evidence_file`, calls
  `manage.py verify_rewrite_exemption`, and passes only when that
  command exits 0.
* If `total >= 300`, verifies every category is 15 or higher.
* Otherwise hard-block with a Rule-F three-part FAIL message.

Pure-docs commits (no files under `backend/`, `frontend/`, `services/`,
`scripts/`, `.githooks/`, `docs/specs/`, `docs/adr/`) are exempt
because they cannot contribute to the rewrite roadmap.

## JSON schema for `docs/rewrite-evidence/<session-id>.json`

```
{
  "session_id": "<uuid-or-handoff-timestamp>",
  "touched_paths": ["backend/apps/.../...", ...],
  "python_lines_remaining": <int>,
  "python_island_declared_in_sticky": <bool>,
  "baseline": {
    "metric": "p95_latency_ms" | "throughput_rps" | "completion_time_ms",
    "value": <float>,
    "source": "pyroscope" | "otel_profiles" | "benchmark",
    "function": "<symbol-name>",
    "workload": "<description>",
    "captured_at": "<ISO8601>"
  },
  "projection": {
    "method": "model" | "extrapolation" | "prior_benchmark",
    "projected_value": <float>,
    "projected_gain_pct": <float>,
    "threshold_pct": 30.0,
    "verdict": "tiny_gain_or_no_python_remains" | "rewrite_required"
  },
  "citations": ["<DOI|URL|RFC|ISO>", ...]
}
```

`verify_rewrite_exemption` recomputes `projected_gain_pct` from
`baseline.value` and `projection.projected_value` and refuses the
exemption if the recomputed value does not match the supplied
`projected_gain_pct` within ±0.01 (floating-point tolerance) or if the
gain is ≥ `threshold_pct`.

## Source backing

* **Beck, K. (2002).** *Test Driven Development: By Example.* Addison-
  Wesley. ISBN 978-0321146533. Establishes the discipline that every
  behavior change ships with a test; the rewrite-quota rule extends
  that discipline to structural progress on the modernization roadmap.
* **Parnas, D.L. (1972).** *On the Criteria To Be Used in Decomposing
  Systems into Modules.* Communications of the ACM 15(12):1053-1058.
  doi:10.1145/361598.361623. Establishes the modularity principles
  that "improve the modular monolith" appeals to.
* **ISO/IEC/IEEE 29119-3:2021.** *Software and systems engineering —
  Software testing — Part 3: Test documentation.* Defines the test
  documentation requirements that the evidence-file schema honors.
* **Brooks, F.P. Jr. (1995).** *The Mythical Man-Month.* Addison-
  Wesley. ISBN 978-0201835953. Chapter "No Silver Bullet" establishes
  that gains below roughly one third rarely justify the architectural
  disruption of a rewrite versus a focused refactor.

## Behavior tests

`.githooks/test_check_rewrite_quota.py` covers 9 scenarios:

1. `total >= 300` with all 20 categories at or above 15 passes.
2. `total > 300` with all 20 categories at or above 15 passes.
3. `total < 300` without exemption blocks.
4. `total < 300` with valid evidence file passes.
5. `total < 300` with evidence file showing gain >= threshold blocks.
6. `total < 300` with missing evidence file blocks.
7. `[REWRITE QUOTA BOOTSTRAP: commit=introduces-rule]` short-circuits.
8. Pure-docs commit (no code files staged) passes.
9. Multi-violation listing form.

Tests stub the `verify_rewrite_exemption` subprocess via
`unittest.mock.patch`.

## Rollout

This commit (Phase K.2) installs the rule, the verify command, the
hook, the tests, and the spec. The hook fires from the next commit
forward. Phase K.2's own commit carries `[REWRITE QUOTA BOOTSTRAP:
commit=introduces-rule]` as its exemption.
