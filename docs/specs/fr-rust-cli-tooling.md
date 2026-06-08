# FR — Rust CLI tooling (`xftool`) framework + catalog

[SPEC FRESHNESS: reviewed_at=2026-06-07 next_review=2026-06-30]
[SPEC CITED: feature=rust-cli-tooling kind=technical_doc id=https://docs.rs/clap verified_at=2026-06-07]

Companion to [ADR 0008](../adr/0008-tooling-languages-rust-cli-python.md). Defines the single Rust
CLI multi-tool (`xftool`), its conventions, and the **catalog** of subcommands — the prioritized,
growing backlog the toolkit is built from (target: 1000+ subcommands, delivered in waves, each one
real and reused, never a stub).

## Sources of truth

- clap (Rust arg parser), <https://docs.rs/clap> — the command framework.
- The existing app crates the tools reuse (no reimplementation): `rust/extensions/*`, the §G ranking
  crates (`ranking_core`, `ranking_profiles`, `ranking_features`, `search_index`, …), and the Python
  management-command layer for ORM/migration/DB-state tools.
- DuckDB <https://duckdb.org>, Polars <https://pola.rs>, ripgrep <https://github.com/BurntSushi/ripgrep>,
  jq <https://jqlang.github.io/jq/> — utilities/libraries invoked by tools (ADR 0008 §4).

## Framework

- **One binary, many subcommands.** `rust/tools/` crate, `[[bin]] name = "xftool"`. Subcommands are
  grouped (`xftool ranking diff`, `xftool index audit`, `xftool log cluster-errors`, …) via clap
  derive. Library-only logic lives in the reused crates; `xftool` is a thin front-end (DRY, ADR 0008 §2).
- **Tooling, not app.** Lives under `rust/tools/`; the Django app and the kernel crates **never**
  depend on it. It is for CI / forensics / cleanup / auditing only.
- **Subcommand contract (every tool obeys):**
  - **Deterministic & read-only by default.** A tool that mutates state requires an explicit
    `--apply` (dry-run is the default), mirroring the repo's `--dry-run` management-command rule.
  - **Machine-readable output.** `--format json|table|csv` (default `table`); JSON for CI.
  - **CI exit codes.** `0` ok, `1` findings/violations, `2` usage/internal error.
  - **No host assumptions.** Cross-platform; paths resolved from the repo root; no PowerShell.
  - **Reuse, don't reimplement.** A ranking/score/artifact/profile tool calls the existing crate; a
    DB/migration/ORM tool shells the matching Django management command; a CSV/Parquet tool uses
    DuckDB/Polars; a text/log scan uses ripgrep.
- **Self-documenting catalog.** `xftool list [--category <c>] [--format json]` prints the catalog;
  `xftool <cmd> --help` documents each. The catalog below is the backlog this is generated from.
- **CI integration.** CI calls `xftool ci <suite>` to run a curated set of check subcommands; each
  emits JSON consumed by the existing gauntlet.

## Build & ship

- Built via the same Dell cargo path as the kernels (`/usr/bin/bash scripts/dell-rust.sh build -p xftool`);
  MSI never compiles. A release binary is content-addressed into the artifact store like the kernels,
  and a `xftool` shim on PATH invokes it. No host toolchain.

## Wave / priority plan (how 1000 is reached honestly)

1. **Wave 0 — framework + the named tools — BUILT 2026-06-07** (`rust/tools/`, binary `xftool`):
   the `xftool` clap skeleton (grouped `xftool <group> <verb-noun>` architecture, shared
   output/format module, `xftool list` catalog) plus **8 working subcommands**:
   `ranking diff`, `score validate-breakdown`, `artifact check`, `index audit`, `bench summarize`,
   `weights lint`, and two buildable-now extras `log cluster-errors` and `store gc-report`. Each
   ships `#[cfg(test)]` unit tests + a `tests/fixtures/` sample and an end-to-end CLI test; all green
   on Dell (`fmt --check`, `clippy -p xftool --all-targets -- -D warnings`, `test -p xftool`).
   **Still pending in a later wave:** the Python `schema_migration_checker` management command (needs
   Django/the ORM, so it is a Python management command per ADR 0008 §3, not a Rust subcommand), and
   the §G-crate-backed refactor of `ranking`/`score`/`artifact`/`index`/`weights` to reuse the
   `ranking_core` / `ranking_profiles` / `search_index` crates once those exist (Wave 0 is standalone
   over files/JSON, with a `NOTE` in each module marking the reuse point).
2. **Wave 1 — the high-value checks** already implied by the repo's gauntlet + observability (≈60–120
   tools): the CI-check, governance-DB, log-forensics, and data-cleanup categories below.
3. **Waves 2…N — breadth by category**, one category per wave, each tool reusing a crate or a
   management command, until the catalog is exhausted. Tools that turn out to duplicate an existing
   command are dropped from the catalog (KISS/DRY), not stubbed.

Each wave is built + tested on Dell and added to `xftool list`. The number grows because adding a
reuse-based subcommand is cheap — not because stubs are generated.

## Catalog (categories, targets, seed tools)

> Target counts are aspirational ceilings per category; the sum exceeds 1000. The seed lists below are
> representative, not exhaustive — each category is filled out in its wave. Names use
> `group verb-noun` shape (the clap subcommand path).

### 1. Ranking & scoring validity — target ~80
`ranking diff` (two runs), `ranking regression-detect`, `ranking topn-stability`, `ranking
order-diff`, `score validate-breakdown`, `score sum-check`, `score nan-inf-scan`, `score
bounds-check`, `score distribution-summary`, `score per-signal-contribution`, `score
explain-dump`, `rerank determinism-check`, `fusion weight-trace`, `penalty audit`, `diversity
audit`, `dedup-suppression audit`, `score-breakdown snapshot`, `score-breakdown compare`, …

### 2. Weight profiles & governance — target ~70
`weights lint`, `weights never-zero-check`, `weights movement-budget-audit`, `weights
monotonicity-check`, `weights compatibility-check`, `profile promotion-eligibility`, `profile
rollback-validity`, `profile status-dump`, `profile diff`, `governance verdict-explain`,
`governance reason-code-audit`, `governance expired-scan`, `meta-algo registry-audit`, `tunable
registry-audit`, `tunable bounds-check`, …

### 3. Artifacts & models — target ~60
`artifact check`, `artifact hash-verify`, `artifact schema-validate`, `artifact version-audit`,
`artifact store-gc-report`, `artifact orphan-scan`, `model codebook-validate`, `model
quantization-roundtrip`, `model shape-check`, `model registry-audit`, `wheel verify`, `so
runtime-path-classify` (rust vs cpp), …

### 4. Search index — target ~60
`index audit`, `index freshness-check`, `index rebuild-estimate`, `index doc-count-verify`,
`index query-explain`, `index relevance-spotcheck`, `index stale-segment-scan`, `index
schema-validate`, `index size-report`, `index missing-doc-scan`, …

### 5. Feature normalization & evidence — target ~50
`features registry-audit`, `features missing-value-policy-check`, `features range-check`, `features
vector-validate`, `features drift-report`, `evidence replay-validate`, `evidence label-validate`,
`evidence provenance-audit`, `evidence guardrail-check`, …

### 6. Schema, migrations & DB (Python mgmt commands) — target ~70
`schema_migration_checker`, `migration_drift_detector`, `fk_on_delete_auditor`, `model_index_auditor`,
`unique_constraint_auditor`, `orphan_fk_scan`, `migration_squash_advisor`, `dangling_table_finder`,
`pgvector_index_auditor`, `db_bloat_report`, `slow_query_extractor`, `pg_stat_top`, … (these need the
ORM/migration graph → Django management commands, not Rust, per ADR 0008 §3.)

### 7. Benchmarks & performance — target ~60
`bench summarize`, `bench regression-gate`, `bench compare-runs`, `bench three-size-check`, `perf
hot-path-list`, `perf flamegraph-summarize`, `perf pyroscope-top`, `perf otel-profile-summarize`,
`perf budget-check`, `perf 20x-gate-report`, …

### 8. Logs & forensics — target ~80
`log cluster-errors`, `log timeline-build`, `log request-trace`, `log error-rate`, `log
top-exceptions`, `log slow-requests`, `log grep` (ripgrep front-end), `log since`, `log between`,
`log dedup`, `log glitchtip-summarize`, `log loki-query`, `log tail-structured`, `log
correlate-trace`, …

### 9. Observability — target ~60
`obs metric-spec-validate`, `obs dashboard-link-check`, `obs alert-rule-audit`, `obs span-audit`,
`obs trace-profile-correlation`, `obs stack-health`, `obs vmalert-summarize`, `obs
otel-collector-config-check`, …

### 10. Data cleanup, retention & dedup — target ~70
`data orphan-row-find`, `data duplicate-artifact-prune` (`--apply`), `data retention-policy-audit`,
`data stale-embedding-find`, `data supersede-old-signals`, `data temp-artifact-gc`, `data
stage-folder-prune`, `data old-snapshot-prune`, `data autoissue-spam-report`, …

### 11. Embeddings & content — target ~40
`embed cost-summarize`, `embed gate-decision-audit`, `embed bakeoff-report`, `embed dim-verify`,
`content passage-dedup-check`, `content metric-snapshot-summarize`, …

### 12. AutoIssues & paper-trail — target ~50
`issues summarize`, `issues by-source`, `issues retire-removed-language` (`--apply`), `issues
bulk-triage`, `issues lesson-coverage`, `issues quota-status`, `papertrail audit`, `papertrail
drought-report`, `papertrail evidence-check`, …

### 13. CI checks & commit-gauntlet helpers — target ~80
`ci marker-validate` (the handoff markers), `ci tdd-cycle-check`, `ci coverage-floor-check`, `ci
mutation-survivor-summarize`, `ci registry-read-verify`, `ci removed-language-scan`, `ci
dead-code-on-replace`, `ci perf-proof-check`, `ci spec-citation-check`, `ci glossary-acronym-check`,
`ci pre-commit-dry-run`, `ci marker-extract`, …

### 14. Repo hygiene & dead code — target ~70
`repo dead-code-find`, `repo unused-import-scan`, `repo long-function-find`, `repo dup-block-find`,
`repo cyclomatic-report`, `repo license-header-check`, `repo todo-audit`, `repo orphan-file-find`,
`repo import-graph-audit`, `repo circular-import-scan`, `repo big-file-find`, …

### 15. Dependency, license & security — target ~50
`deps audit` (cargo-audit/pip-audit front-end), `deps cve-check`, `deps sbom-generate`, `deps
outdated`, `deps license-scan`, `deps duplicate-versions`, `secrets scan`, `deps lockfile-verify`, …

### 16. Config & compose integrity — target ~40
`config schema-validate`, `config env-var-audit`, `compose integrity-check`, `compose
glitchtip-guard`, `compose orphan-volume-find`, `config routing-validate` (mutation-routing.json),
`config protected-stores-check`, …

### 17. Docs & glossary — target ~40
`docs link-check`, `docs glossary-coverage`, `docs spec-freshness-audit`, `docs adr-index`, `docs
orphan-find`, `docs dup-content-find`, `docs citation-verify`, …

### 18. Build & artifact store — target ~40
`store gc-report`, `store gc` (`--apply`), `store content-verify`, `store active-symlink-audit`,
`store size-report`, `kernel sync-from-dell` (front-end to the sync script), `kernel
runtime-import-check`, …

### 19. Cross-machine (Dell/Mint) ops — target ~30
`dell reachable`, `dell quality-shard-status`, `dell sonar-status`, `mint quality-status`, `turbo
mutation-status`, `routing weights-report`, …

### 20. Frontend / asset checks — target ~30
`fe deep-link-catalog-audit`, `fe pehelper-coverage`, `fe chart-state-audit` (truthful states), `fe
bundle-size-report`, `fe token-usage-check` (no hardcoded hex), `fe a11y-spotcheck`, …

> Sum of targets ≈ 1100. The catalog is the living backlog; `xftool list` is generated from it.

## Glossary

- **`xftool`** — the single Rust command-line multi-tool; one binary, many grouped subcommands.
- **clap** — the Rust library that parses command-line arguments and generates `--help`.
- **subcommand** — one tool inside `xftool` (e.g. `xftool ranking diff`).
- **DuckDB / Polars / ripgrep / jq** — invoked utilities/libraries (ADR 0008 §4), not languages.
- **dry-run / `--apply`** — read-only by default; a mutating tool acts only with explicit `--apply`.
