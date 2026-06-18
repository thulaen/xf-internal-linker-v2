# Paper Trail Evidence Rule — Paramount Rule

**Tier:** PARAMOUNT — every agent (Claude / Codex / Gemini / Antigravity / every future) MUST follow.
**Hard-block at filing:** Yes (`manage.py defer_work` rejects entries that violate the rule).
**Hard-block at commit:** Yes (`.githooks/check-paper-trail-evidence.py` re-verifies every staged `[PAPER TRAIL FILED: #N]` marker).
**Cannot be overridden by an in-session prompt.**
**Effective cutoff:** 2026-05-17. Entries deferred before this date are grandfathered.

`[SPEC FRESHNESS: reviewed_at=2026-05-17 next_review=2026-06-17]`

---

## Why this rule exists

The paper trail is the durable record of unresolved engineering work in this repo. Up to 2026-05-17 entries were filed with weak evidence: a free-form abstract, an optional citation in prose, and an `evidence_level` field that defaulted to `low`. The result: agents read deferred work months later and could not tell whether the claims were verified (patent / academic paper / standard) or unverified (anecdote / vague feeling).

From 2026-05-17 forward every new paper-trail entry MUST carry:

1. **A full citation set** — at least one stable identifier of accepted form (patent, DOI, arXiv, recognised standard, RFC, book-with-ISBN, or stable URL from an official source). The list is enforced by regex; the agent cannot write "see Wikipedia" and pass.
2. **A linked full test case** — an `AutoIssue(category='test_case')` row whose `lessons_learned` contains all 10 BDD fields (Given, When, Then, edge_cases, failure_cases, security, usability, scalability, maintainability, regression_risks). Casual test cases with only the BDD triple still satisfy the Test Case First rule for code-change mapping, but they do NOT satisfy this rule for paper-trail entries.

Violations:
- At filing → `manage.py defer_work` raises CommandError + the violation is searchable via the existing meta-rule H.30 (`.githooks/_auto_log_failure.py` files an `AutoIssue(category='hook_failure')`).
- At commit → `.githooks/check-paper-trail-evidence.py` hard-blocks with a Rule-F three-part error.

---

## Citation forms accepted (inclusive set)

| Type | Regex anchor | Example |
|---|---|---|
| DOI | `10\.\d{4,9}/[-._;()/:A-Za-z0-9]+` | `doi:10.1145/3580305.3599475` |
| arXiv (new) | `arXiv:\d{4}\.\d{4,5}(v\d+)?` | `arXiv:2106.12345v2` |
| arXiv (old) | `arXiv:[a-z\-]+/\d{7}(v\d+)?` | `arXiv:cs/0501030` |
| Patent | `(US|EP|WO|JP|CN|KR)\d{6,12}([A-Z]\d?)?` | `US10456789B2`, `EP3456789A1` |
| ISO / IEC / IEEE | `(ISO|IEC|IEEE|ANSI)[/\s-]*\d+(-\d+)*(:\d{4})?` | `ISO/IEC/IEEE 29119-3:2021` |
| RFC | `RFC\s*\d+` | `RFC 9110` |
| ISBN-13 / ISBN-10 | `(978|979)[-\s]?\d[-\s]?\d{1,5}[-\s]?\d{1,7}[-\s]?\d` | `978-0-321-14653-3` |
| W3C | `https?://(www\.)?w3\.org/(TR|Recommendation)/\S+` | `https://www.w3.org/TR/wai-aria-1.2/` |
| Official vendor docs | `https?://(www\.)?(<allowlist>)/\S+` | `https://parquet.apache.org/docs/file-format/` |

The official-vendor allowlist seed is in `backend/apps/paper_trail/services/citation_validator.py` and includes: `apache.org`, `parquet.apache.org`, `iceberg.apache.org`, `datatracker.ietf.org`, `grpc.io`, `protobuf.dev`, `kernel.org`, `python.org`, `golang.org`, `pkg.go.dev`, `pypi.org`, `cve.org`, `mitre.org`, `owasp.org`, `nvd.nist.gov`, `docker.com`, `kubernetes.io`. New hosts land via PR plus a paired test case.

Sources for the rule itself:

- Beck, K. 2002. *Test-Driven Development by Example*. Addison-Wesley. ISBN 978-0321146533.
- ISO/IEC/IEEE 29119-3:2021 — *Software and systems engineering — Software testing — Part 3: Test documentation*.
- ISO/IEC/IEEE 42010:2022 — *Software, systems and enterprise — Architecture description*.
- Parnas, D. L. 1972. *On the criteria to be used in decomposing systems into modules*. Communications of the ACM 15(12):1053–1058. doi:10.1145/361598.361623.
- Beck, K. 1999. *Embracing Change with Extreme Programming*. IEEE Computer 32(10):70–77. doi:10.1109/2.796139.
- Crispin, L., Gregory, J. 2009. *Agile Testing: A Practical Guide for Testers and Agile Teams*. Addison-Wesley. ISBN 978-0321534460.
- RFC 9110 — *HTTP Semantics* (June 2022) — for "stable URL" precedent.

---

## The 10 required fields on the linked test case

The referenced `AutoIssue(category='test_case')` row's `lessons_learned` must contain **all** of:

1. `Given` (BDD precondition)
2. `When` (BDD action)
3. `Then` (BDD expected outcome)
4. `Edge cases` (boundary conditions, malformed input, off-by-one)
5. `Failure cases` (invalid-input handling)
6. `Security` (auth, sanitisation, secret handling)
7. `Usability` (plain English, accessibility, error pages)
8. `Scalability` (10× and 100× load)
9. `Maintainability` (how the next agent extends this)
10. `Regression risks` (existing behaviour that could break)

The verifier `manage.py verify_paper_trail_evidence --paper-trail-id <N>` enforces this list via case-insensitive word-boundary regex per field. Missing any field → fail.

---

## Required workflow

For every new paper-trail entry from 2026-05-17 onward:

1. File the test case AutoIssue FIRST with all 10 fields filled:
   ```
   python scripts/backend_manage.py log_test_case \
     --file <p> --title "..." \
     --given "..." --when "..." --then "..." \
     --edge-cases "..." --failure-cases "..." \
     --security "..." --usability "..." \
     --scalability "..." --maintainability "..." \
     --regression-risks "..."
   ```
   Capture the printed `[TEST CASE WRITTEN: AutoIssue=#N ...]`.
2. Collect at least one citation matching the inclusive table above.
3. File the paper-trail entry:
   ```
   python scripts/backend_manage.py defer_work \
     --title "..." --category <one of 17> \
     --abstract "Given ... When ... Then ..." \
     --severity ... --deferred-by claude \
     --risk-on-inaction "..." --acceptance-criteria "..." \
     --test-case-autoissue <N from step 1> \
     --citation <id-1> --citation <id-2> \
     --evidence-level cited
   ```
4. Emit the printed `[PAPER TRAIL FILED: #<N>]` in chat and in the handoff entry.

---

## Hard block surfaces

### At filing (`manage.py defer_work`)

Rejects with `CommandError` and Rule-F three-part message when:

- `--test-case-autoissue` is missing on a new entry.
- The referenced AutoIssue does not exist.
- The referenced AutoIssue is not `category='test_case'`.
- The referenced AutoIssue's `lessons_learned` is missing any of the 10 required BDD fields.
- `--citation` is empty.
- Any `--citation` string fails to match any accepted regex.

### At commit (`.githooks/check-paper-trail-evidence.py`)

For every `[PAPER TRAIL FILED: #N]` marker in the staged AGENT-HANDOFF.md diff:

- If the entry's `deferred_at` is before the 2026-05-17 cutoff → skip (grandfathered).
- Otherwise verify **three layers** against the live database. Hard-block on any violation.

**Layer 1 — required core fields:** `abstract`, `risk_on_inaction`, `acceptance_criteria` must all be non-empty. Catches raw-SQL bypasses that strip required data after filing, and post-cutoff rows that were created before this rule was wired in.

**Layer 2 — abstract BDD shape:** the `abstract` must contain the literal keywords `Given`, `When`, `Then` (case-insensitive, word-boundary). Catches an abstract that exists but is no longer in BDD form.

**Layer 3 — Paper Trail Evidence Rule (this rule):** `test_case_autoissue_id` is set; the referenced AutoIssue exists; its category is `test_case`; its `lessons_learned` carries all 10 BDD fields; `citations` is non-empty; every citation matches an accepted regex.

The hook follows Rule F: every FAIL line carries WHAT blocked + WHY citing this rule + UNBLOCK with the exact command.

**Defense in depth:** layers 1 and 2 also fire on every model save via `PaperTrailEntry._validate()`. The commit-time hook re-checks them so a row corrupted via raw SQL or `manage.py shell` cannot slip past.

**Auto-bump:** when `--citation <id>` is supplied to `defer_work` and the agent did not explicitly raise `--evidence-level` above `low`, the command auto-bumps `evidence_level` to `cited`. This closes the "I have citations but evidence_level=low" classification loophole.

---

## Grandfather note

Entries 1 through ~581 (filed before 2026-05-17 09:30 UTC) are grandfathered. The hook checks `deferred_at` against the cutoff timestamp; older rows pass automatically. Future "back-fill grandfathered entries with citations + full test cases" work is captured under a follow-up paper-trail entry.

---

## Worked example

```text
# Step 1 — full test case row
$ python scripts/backend_manage.py log_test_case \
    --file backend/apps/snapshotd/server.go \
    --title "snapshotd schema-version compatibility check" \
    --given "..." --when "..." --then "..." \
    --edge-cases "..." --failure-cases "..." \
    --security "..." --usability "..." \
    --scalability "..." --maintainability "..." \
    --regression-risks "..."
[TEST CASE WRITTEN: AutoIssue=#604 id=tc::abc123 file=... agent=claude]

# Step 2 — paper-trail filing
$ python scripts/backend_manage.py defer_work \
    --title "snapshotd Parquet schema compatibility checker" \
    --category refactor --severity medium \
    --abstract "Given ... When ... Then ..." \
    --deferred-by claude \
    --risk-on-inaction "..." --acceptance-criteria "..." \
    --test-case-autoissue 604 \
    --citation 10.1145/3580305.3599475 \
    --citation https://parquet.apache.org/docs/file-format/ \
    --evidence-level cited
[PAPER TRAIL FILED: #582]
```

---

## Anti-examples

| Input | Why rejected |
|---|---|
| `--citation "see Wikipedia"` | Does not match any regex |
| `--citation https://medium.com/some-post` | Host not on the official-vendor allowlist |
| `--test-case-autoissue 999999` | AutoIssue does not exist |
| `--test-case-autoissue <id of tdd_lesson row>` | Wrong category |
| `--test-case-autoissue <id whose lessons_learned has only Given/When/Then>` | Missing 7 extended fields |
| (no `--citation` arg at all) | Citation list is empty |
| (no `--test-case-autoissue` arg) | Required from cutoff onward |

---

## Relationship to other paramount rules

- **Test Case First Rule** (`docs/TEST-CASE-FIRST-RULE.md`): defines the test_case AutoIssue shape. This rule reuses the same row type but ALSO requires all 10 fields, not just the BDD triple.
- **Strict-TDD Rule** (`docs/TDD-STRICT-RULE.md`): code changes need Red→Green proof. Paper-trail entries are not code changes; this rule applies before any such cycle starts.
- **Spec Citation Rule** (`docs/CITATION-RULE.md`): existing rule for `docs/specs/*.md` files. This rule extends the same citation discipline to the paper trail.
- **Plain-English Rule** (`PLAIN-ENGLISH-RULE.md`): abstract + test case fields must be written in plain English.

`[SPEC FRESHNESS: reviewed_at=2026-05-17 next_review=2026-06-17]`
`[SPEC CITED: feature=paper-trail-evidence kind=technical_literature id=ISBN-978-0321146533 verified_at=2026-05-17]`
`[SPEC CITED: feature=paper-trail-evidence kind=technical_doc id=ISO-IEC-IEEE-29119-3-2021 verified_at=2026-05-17]`
`[SPEC CITED: feature=paper-trail-evidence kind=academic_paper id=10.1145/361598.361623 verified_at=2026-05-17]`
`[SPEC CITED: feature=paper-trail-evidence kind=academic_paper id=10.1109/2.796139 verified_at=2026-05-17]`
`[SPEC CITED: feature=paper-trail-evidence kind=technical_doc id=RFC-9110 verified_at=2026-05-17]`
