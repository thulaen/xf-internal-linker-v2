# FR — Root-Cause Clustering of AutoIssues

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

[SPEC CITED: feature=root-cause-clustering kind=academic_paper id=doi:10.1109/ICWS.2017.13 verified_at=2026-05-29]
[SPEC CITED: feature=root-cause-clustering kind=academic_paper id=doi:10.1109/SEQUEN.1997.666900 verified_at=2026-05-29]
[SPEC CITED: feature=root-cause-clustering kind=academic_paper id=doi:10.1145/276698.276876 verified_at=2026-05-29]
[SPEC CITED: feature=root-cause-clustering kind=academic_paper id=doi:10.1145/509907.509965 verified_at=2026-05-29]
[SPEC CITED: feature=root-cause-clustering kind=academic_paper id=doi:10.1007/978-3-642-37456-2_14 verified_at=2026-05-29]
[SPEC CITED: feature=root-cause-clustering kind=academic_paper id=acm:10.5555/2337223.2337364 verified_at=2026-05-29]
[SPEC CITED: feature=root-cause-clustering kind=technical_literature id=isbn:978-1108476348 verified_at=2026-05-29]

## Summary (plain English)

The AutoIssue table holds 568 open issues. Many of them are the **same
underlying problem reported many times** — for example, 110 GlitchTip
runtime errors and 115 mutation-survivor rows that cluster into a much
smaller number of real root causes. Today the system only collapses
issues that share an **exact** fingerprint (`canonical_fingerprint`), so
near-duplicates that differ by a number, a path, or a stack frame stay as
separate rows.

**Root-cause clustering** groups near-duplicate issues into clusters so
that fixing one representative issue closes the whole family. It does this
by (1) turning each issue's text into a stable *template*, (2) building a
*signature* of that template plus the issue's affected files and stack
frames, (3) finding candidate near-duplicates cheaply, (4) measuring real
similarity, and (5) grouping issues above a tuned similarity threshold.

This is a **decision-support** feature: it proposes clusters; an agent
still reviews each cluster before resolving the members. It never
auto-resolves a row on its own.

## Source of truth (citations)

| Step | Technique | Citation |
|------|-----------|----------|
| Template extraction | Drain (fixed-depth parse tree, online log parsing) | He, Zhu, Zheng, Lyu, *Drain: An Online Log Parsing Approach with Fixed Depth Tree*, ICWS 2017 — **doi:10.1109/ICWS.2017.13** |
| Stack-trace grouping | ReBucket (call-stack similarity for duplicate crash reports) | Dang, Wu, Zhang, Zhang, *ReBucket*, ICSE 2012 — **ACM 10.5555/2337223.2337364** |
| Signature / resemblance | MinHash (Jaccard estimation by min-wise hashing) | Broder, *On the Resemblance and Containment of Documents*, SEQUENCES 1997 — **doi:10.1109/SEQUEN.1997.666900** |
| Candidate generation | Locality-Sensitive Hashing (banding) | Indyk, Motwani, STOC 1998 — **doi:10.1145/276698.276876** |
| Alt. signature | SimHash | Charikar, STOC 2002 — **doi:10.1145/509907.509965** |
| Clustering | HDBSCAN (density-based hierarchical) | Campello, Moulavi, Sander, PAKDD 2013 — **doi:10.1007/978-3-642-37456-2_14** |
| Shingling + MinHash + LSH banding reference | *Mining of Massive Datasets*, 3rd ed., Ch. 3 | Leskovec, Rajaraman, Ullman — **ISBN 978-1108476348** |

## The pipeline

Each AutoIssue contributes: `issue_title`, `issue_body`, `affected_files`
(list of repo-relative paths), an optional stack trace, and `source`.

1. **Template extraction (logic).** Run Drain over title+body to produce a
   constant template with variable slots masked (numbers, hex, UUIDs,
   paths → placeholders — reuse the existing normalisation in
   `backend/apps/auto_issues/services/fingerprinting.py` and
   `backend/apps/audit/error_ingest.py`). For rows with a stack trace,
   normalise frames to `module.function` (drop addresses and line numbers)
   per ReBucket.
2. **Feature/shingle (logic).** Build a feature set = k-shingles (k=5,
   matching the existing C++ kernel) of the template ∪ the set of affected
   file paths ∪ the top-N normalised stack frames.
3. **Candidate generation (speed-critical compute).** Compute a MinHash
   signature (m=64) per issue and band it into LSH buckets (b=8, r=8) so
   only issues sharing a bucket are compared. This avoids the O(n²)
   all-pairs comparison across 600 issues.
4. **Exact similarity + threshold (logic).** For each candidate pair,
   compute a blended score = weighted Jaccard of (template ⊕ paths)
   combined with ReBucket-style stack-frame proximity. Accept edges above
   a tuned threshold τ (default **0.80**, range 0.70–0.85; matches the C++
   kernel's 0.85 default with headroom).
5. **Cluster (logic).** Treat accepted pairs as edges of a sparse graph and
   group with single-link agglomeration (or HDBSCAN over the candidate
   distance matrix). Each connected component is one root-cause cluster;
   the highest-`priority_score` member is the representative.
6. **Persist/batch (plumbing).** Read issues in batches, run hashing,
   write cluster assignments, and feed duplicate members through the
   existing `dedup.upsert_dedup` collapse path.

## Language ownership

Per the project's multi-language model and the user directive:

- **Rust = step 3 + 4 speed-critical compute** (MinHash, LSH banding,
  pairwise blended similarity). **CPP-FIRST escalation:** the repo already
  ships a proven C++ MinHash+LSH kernel
  (`backend/extensions/papertrail_dedup.cpp`). A Rust implementation is
  only adopted if it **benchmarks at least as fast** as that C++ kernel on
  the same workload; the benchmark is the native-rewrite escalation
  evidence (`[NATIVE REWRITE REVIEW: ...]`, AutoIssue labelled
  `performance-native-rewrite`). If Rust does not beat the C++ baseline,
  the C++ kernel is reused and Rust is not added.
- **Haskell = steps 1, 2, 4-threshold, 5 logic** (template decisions,
  shingling rules, blend weights, cluster selection).
- **Go = step 6 plumbing** (a gRPC-over-unix-socket service that reads
  issue batches, calls the compute + logic stages, returns cluster
  assignments), mirroring `services/streamd` and satisfying Rule-K's nine
  artefacts.
- **Python/Django = orchestration**: a gRPC client and a
  `cluster_autoissues` management command that pulls open issues, calls the
  service, writes cluster IDs, and collapses duplicates via
  `dedup.upsert_dedup`.

## Behaviour (Given / When / Then)

- **Given** a set of open AutoIssues where several describe the same root
  cause, **When** `cluster_autoissues --dry-run` runs, **Then** it groups
  the near-duplicates into one cluster with a single representative and
  reports members + similarity, changing no rows.
- **Given** two issues whose blended similarity is below τ, **When**
  clustering runs, **Then** they remain in separate clusters.
- **Given** clustering with `--apply`, **When** a duplicate family is
  collapsed, **Then** members route through `dedup.upsert_dedup`
  (occurrence_count bumped, representative kept) and no issue is auto-marked
  `resolved` — resolution stays a separate, agent-reviewed step.

## Acceptance criteria

- `cluster_autoissues --dry-run` produces deterministic clusters for a
  fixed input (same seed → same clusters).
- Candidate generation is sub-quadratic (LSH buckets, not all-pairs).
- The similarity threshold τ is configurable and defaults to 0.80.
- The compute stage meets its language's mutation-kill gate; the Go
  service satisfies Rule-K; the spec's citations resolve via
  `manage.py cite_spec`.
- No row is auto-resolved by clustering.

## Non-goals

- Not a replacement for exact `canonical_fingerprint` dedup; it sits on top.
- Not an auto-resolver. Clusters are proposals.
- Not a ranking-domain feature (see `fr014-near-duplicate-destination-clustering.md`
  for the unrelated destination-clustering feature).
