# FindBugs Observability BDD Test Cases

## Duplicate During Observability Degradation

Given a Rust report repeats an existing bug candidate and the report metadata
says observability is degraded, when Django imports the report, then it updates
the existing bug row and creates one FindBugs-health row instead of duplicate
bug noise.

## Artifact Retention

Given the FindBugs artifact folder contains files older than 8 days or larger
than the 1 GB cap, when the prune task runs, then stale files are deleted and
protected repository roots are refused.

## Operator Page

Given `/find-bugs` loads with open Rust defect AutoIssues, when the page renders,
then D3 charts show severity counts and the table shows one deduped row per
canonical fingerprint.

## Haskell Null-State Sidecar

Given Rust AST facts assign a variable null on one path and not-null on another,
when the Haskell sidecar joins the states, then the output state is Unknown and
the analysis terminates.

## Advisory Model Confirmation

Given SmolLM2 proposes a suspicious pattern while embeddings are idle, when no
Rust or Haskell rule confirms it, then no AutoIssue is filed.
