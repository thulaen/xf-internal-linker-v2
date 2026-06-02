<!-- Spec metadata (machine-read by .githooks/check-spec-citation.py). The body below is the curated library ledger; agents do NOT read it in full at session start (see docs/library-bank/AGENT-BOOT-BRIEF.md). -->
[SPEC CITED: feature=fr-approved-library-expansion-bank kind=technical_doc id=https://arrow.apache.org/docs/ verified_at=2026-05-30]
[SPEC CITED: feature=fr-approved-library-expansion-bank kind=technical_doc id=https://www.postgresql.org/docs/current/textsearch.html verified_at=2026-05-30]
[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

# Approved Library Expansion Bank and Modular-Monolith Reuse Plan
Status: revised implementation reference.
Target length: 36,000 to 42,000 words.
Library ceiling: 256 unique entries.
Purpose: give agents a durable knowledge base for choosing libraries by capability instead of reinventing wheels or installing random packages.

## 1. Executive directive

This document replaces the earlier short library list. It defines a reusable library bank, acceptance gates, capability recipes, and copy-pasteable implementation slices. Agents must use it as a reference guide, not as an install-all backlog. The plan favors modular-monolith ownership, clear boundaries, benchmark evidence, and explicit failure states. It does not allow hidden fallbacks, cosmetic wiring, unowned dependencies, or live-path machine-learning creep.

Every library in this document must enter through one owning module. The owner exposes a public API, validates inputs, records provenance, publishes health, and owns repair commands. Other modules call that API. They must not import private files, call sidecar clients directly, read internal stores, or construct duplicate data paths. A library remains a candidate until a slice accepts it with tests, benchmarks, license review, resource rules, and no-fallback proof.

The plan avoids hardcoded hostnames, fixed model families, fixed helper machines, fixed thresholds, fixed budgets, and fixed library winners. It defines registries, policies, bake-offs, and capability recipes. Future agents should ask, 'What capability do I need?' Then they should choose from the relevant bank, run the acceptance gates, and wire the library through the owner module.

## 2. Binding architecture rules

1. Use one canonical path per product behavior. Do not keep a new path and an old path after acceptance.
2. Fail closed when a required module, native artifact, schema, or evidence store is missing. Return blocked, repair-required, rebuild-required, or access-denied states instead of pretending success.
3. Keep Python as orchestration, admin, report generation, migration glue, and approved offline integration. Do not let Python own correctness, hot-path compute, service plumbing, ranking decisions, or native fallbacks.
4. Use Haskell for correctness, domain invariants, deterministic validation, ranking governance, and profile promotion decisions.
5. Use Go for workers, queues, transport, service wiring, repair-job shells, API boundaries, streaming, and imperative plumbing.
6. Use C++ or Rust for compute-heavy kernels only after benchmark evidence proves the fit. C++ and Rust must produce compiled artifacts and health-checkable binaries or shared libraries.
7. Use Lua only for bounded embedded policy overlays, templates, reason codes, capped deltas, and extension surfaces. Lua must not compute final rank, validate domain invariants, own queues, or bypass governance.
8. Use TypeScript and React for display, forms, local UI state, and noob-friendly truth screens. The browser must not compute governance outcomes.
9. Use metadata_catalog, schema_registry, provenance, access_policy, backpressure, work_routing, coordination, evidence, and search_index APIs rather than bypassing their owned domains.
10. Treat helper PCs as accelerators. They may run shards, tests, benchmarks, and offline trials. They must not own truth, promotion, source-of-record storage, or irreversible writes.

## 3. Acceptance gates for every new library

1. Owner gate. The slice names the owning module, public API, private engine path, allowed callers, and forbidden callers.
2. License gate. The slice records license, source URL, package version, lock hash, and review status.
3. Security gate. The slice runs vulnerability and secret checks where applicable and records accepted risks.
4. Spec gate. The slice cites an official specification, academic paper, patent, or primary documentation source before coding.
5. TDD gate. The first implementation action creates failing tests that express the desired behavior and boundary.
6. Benchmark gate. Replacements of Python hot paths benchmark small, medium, and large inputs. Native replacements need at least five times speedup over the Python path unless the slice records a formal performance exemption.
7. Resource gate. The slice defines RAM, CPU, disk, parallelism, and helper-PC policy before running heavy work.
8. No-fallback gate. The old path disappears in the same accepted work unit, or the new library remains candidate-only.
9. Health gate. Required compiled artifacts, services, contracts, and indexes appear in module health checks.
10. Documentation gate. The slice updates ADR, PRD, recipes, operator runbook, and agent prompt guidance where relevant.

## 4. Capability recipes

### Need live vector retrieval

Use search_index.api with pgvector first. Use USearch, hnswlib, LanceDB, Qdrant, or DiskANN only in a bake-off slice that records recall, latency, RAM, disk, and rebuild cost. Keep FAISS only for existing approved callers and delete degraded fallback branches.

### Need full-text search without JVM

Use Tantivy or Postgres full-text candidates behind search_index.api. Use Quickwit for immutable logs or archives, not live ranking. Use Meilisearch or Typesense only for admin UX comparison.

### Need high-volume JSON import

Use simdjson plus simdutf in native ingest. Validate schemas through schema_registry. Keep Python orchestration for command flow and reject invalid records rather than silently repairing them.

### Need Unicode-safe text processing

Use simdutf for validation, ICU4C for locale semantics, ftfy for recorded offline repair, and uchardet only when charset metadata is absent. Never let text normalization differ by language without fixtures.

### Need duplicate detection

Use BLAKE3 or XXH3 for fast fingerprints, MinHash or SimHash kernels for approximate similarity, and CRoaring for candidate sets. Benchmark Rust and C++ contenders and keep the faster accepted path.

### Need graph diagnostics

Use Apache AGE for stored graph snapshots, GraphBLAS or NetworKit for heavy offline metrics, NetworkX for small reference fixtures, and Haskell governance for acceptance decisions.

### Need offline ranking model candidates

Use LightGBM, CatBoost, XGBoost, Optuna, and SHAP behind ranking_training.api. Export only artifacts that pass schema, provenance, runtime compatibility, Haskell governance, and GUI approval.

### Need constrained optimization

Use CVXPY, OR-Tools, OSQP, HiGHS, Z3, or cvc5 in offline diagnostics. Store infeasible constraints and solver settings as evidence. Never let a solver promote active profiles.

### Need native C++ speed

Use CMake, Ninja, Google Benchmark, sanitizers, Perfetto, GWP-ASan, clang-tidy, and fuzzing. Register the artifact in compiled artifact health checks and delete Python fallback in the same work unit.

### Need Rust speed

Use cargo-nextest, Criterion.rs, proptest, Miri, Kani, cargo-fuzz, and cargo-mutants. Rust wins only with recorded benchmark proof and ownership fit.

### Need Go worker plumbing

Use go-redis, Redis Streams, Redis sorted sets, River or Asynq only as benchmark candidates, ConnectRPC for APIs, pprof, and OpenTelemetry Go. Do not put ranking or correctness logic in Go.

### Need browser UI quality

Use TanStack Query, TanStack Table, React Hook Form, Zod or Valibot, XState, Radix UI, shadcn/ui, Playwright, Vitest, React Testing Library, MSW, and axe-core. Browser code displays truth; it does not decide truth.

### Need supply-chain control

Use Syft, Grype, Trivy, OSV-Scanner, pip-audit, cargo-audit, cargo-deny, Cosign, SLSA, in-toto, and secret scanners. Treat scanner output as review input with severity policy.

### Need documentation agents can reuse

Use MkDocs or mdBook, Mermaid, markdownlint, Vale, ADR indexes, owner-module tables, and copy-pasteable slices. Keep docs close to tests and implementation files.

## 5. Library registry

This registry contains exactly 256 unique entries. It does not order agents to install every library. It gives a scoped choice bank. Use candidate libraries only through the relevant slice and acceptance gates.

### A. Columnar and dataset execution

#### 001. Apache Arrow
- Lane: C++/Rust/Python via ranking_training, metadata_catalog.
- Use: share columnar memory, define typed feature rows, move batches between Rust, C++, and Python without bespoke row serializers.
- Avoid: use it as the active profile store or as an ungoverned schema authority.
- Pair: Parquet, DataFusion, DuckDB, Polars.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 002. Arrow Acero
- Lane: C++ via ranking_training native execution.
- Use: run in-process C++ columnar execution for feature transforms that prove they need native speed.
- Avoid: replace governance checks or Django orchestration.
- Pair: Arrow, Parquet, Google Benchmark.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 003. Apache Parquet
- Lane: C++/Rust/Python via metadata_catalog, ranking_training.
- Use: store versioned feature rows, evidence extracts, replay corpora, and drift windows in compact columnar files.
- Avoid: store secrets, raw labels that privacy policy forbids, or active runtime state.
- Pair: Arrow, DuckDB, Polars.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 004. DuckDB
- Lane: C++/Python via ranking_training.
- Use: join local Parquet evidence, run offline analytics, and produce deterministic reports on the Dell box.
- Avoid: serve live suggestions or own profile activation.
- Pair: Parquet, Ibis, Great Expectations.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 005. Polars
- Lane: Rust/Python via ranking_training.
- Use: build lazy feature pipelines and fast joins where Python orchestration needs a high-speed dataframe engine.
- Avoid: become a hidden production scorer.
- Pair: Arrow, Parquet, DuckDB.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 006. Apache DataFusion
- Lane: Rust via ranking_training experimental engine.
- Use: test Rust-native SQL and dataframe execution against DuckDB and Polars for feature-row construction.
- Avoid: replace Postgres as the system of record.
- Pair: Arrow, Substrait, Parquet.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 007. Substrait
- Lane: Spec via schema_registry, ranking_training.
- Use: represent portable query plans when a feature transform may run in DuckDB, DataFusion, or C++.
- Avoid: hardcode engine-specific plans into business logic.
- Pair: DataFusion, DuckDB, Acero.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 008. Velox
- Lane: C++ via ranking_training native candidate.
- Use: benchmark high-performance vectorized execution for large offline feature workloads.
- Avoid: ship into the live request path without a resource and benchmark gate.
- Pair: Arrow, Substrait, Parquet.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 009. Ibis
- Lane: Python via ranking_training orchestration.
- Use: define backend-portable analytical expressions while keeping Python as orchestration only.
- Avoid: hide backend-specific behavior from tests.
- Pair: DuckDB, DataFusion, Polars.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 010. delta-rs
- Lane: Rust/Python via metadata_catalog.
- Use: version tabular artifacts where append-only history and schema evolution matter.
- Avoid: replace provenance or artifact hashes.
- Pair: Parquet, OpenDAL, lakeFS.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 011. PyIceberg
- Lane: Python via metadata_catalog optional.
- Use: read or write Iceberg-style tables only when a future dataset registry needs table semantics without Spark.
- Avoid: add a JVM table service or hardcode table paths.
- Pair: Parquet, OpenDAL, metadata_catalog.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 012. OpenDAL
- Lane: Rust via metadata_catalog storage adapters.
- Use: abstract local, S3-compatible, and future object storage behind tested storage capabilities.
- Avoid: let modules write arbitrary paths outside metadata_catalog.
- Pair: delta-rs, BLAKE3, provenance.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 013. lakeFS
- Lane: Go service via metadata_catalog optional.
- Use: version large datasets when Git-like data branches become necessary for offline experiments.
- Avoid: be required for correctness or live scoring.
- Pair: OpenDAL, Parquet, provenance.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 014. Lance format
- Lane: Rust/C++ via metadata_catalog, ranking_training.
- Use: store vector and multimodal columns compactly for offline vector experiments.
- Avoid: replace pgvector as the accepted live Stage 1 path.
- Pair: LanceDB, Arrow, Parquet.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 015. LanceDB
- Lane: Rust/Python/TS via ranking_training vector experiments.
- Use: run embedded vector experiments, reranking analysis, and multimodal dataset exploration offline.
- Avoid: silently move live search away from search_index.api.
- Pair: Lance format, USearch, pgvector.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 016. SQLite FTS5
- Lane: C via admin tooling optional.
- Use: build tiny local proof indexes for CLI tests and fixture comparison.
- Avoid: become the product search engine.
- Pair: Tantivy, ripgrep, golden fixtures.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 017. LMDB
- Lane: C via native cache experiments.
- Use: benchmark memory-mapped read-heavy caches for immutable dictionaries or compact lookup tables.
- Avoid: hold mutable business state or bypass Postgres.
- Pair: BLAKE3, mmap, health checks.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 018. RocksDB
- Lane: C++ via offline cache experiments.
- Use: test high-write local key-value workloads for rebuildable offline indexes.
- Avoid: store canonical records that must live in Postgres.
- Pair: OpenDAL, metadata_catalog, repair commands.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### B. Search and retrieval

#### 019. pgvector
- Lane: Postgres extension via search_index.
- Use: run accepted live Stage 1 vector retrieval through HNSW or exact vector search inside Postgres.
- Avoid: fall back to FAISS-GPU or a side service after cutover.
- Pair: Bedrock embeddings, ranking_runtime.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 020. USearch
- Lane: C++/Rust/Go/Python via search_index bake-off.
- Use: benchmark compact HNSW-like vector search and quantization against pgvector for offline evidence.
- Avoid: ship as an unapproved live retrieval path.
- Pair: pgvector, LanceDB, DiskANN.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 021. hnswlib
- Lane: C++/Python via search_index bake-off.
- Use: provide a simple HNSW recall and latency baseline for vector-search tests.
- Avoid: own product indexing or schema.
- Pair: pgvector, USearch, benchmark harness.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 022. FAISS
- Lane: C++/Python via approved library path only.
- Use: keep mature vector library callers that already exist, while deleting degraded Python fallbacks.
- Avoid: recreate FAISS or use GPU-required live retrieval.
- Pair: pgvector, benchmark harness.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 023. DiskANN
- Lane: C++ via offline large-vector experiments.
- Use: test disk-backed approximate nearest neighbor search when vectors outgrow RAM.
- Avoid: become mandatory on small machines.
- Pair: LanceDB, OpenDAL, Parquet.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 024. NGT
- Lane: C++ via search_index benchmark lane.
- Use: compare graph-based vector search against HNSW candidates on fixed corpora.
- Avoid: add a permanent service without winning evidence.
- Pair: pgvector, hnswlib, USearch.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 025. Annoy
- Lane: C++/Python via search_index baseline.
- Use: keep a simple memory-mapped ANN baseline for static corpora and regression tests.
- Avoid: serve mutable live indexes.
- Pair: USearch, HNSW, benchmark harness.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 026. Qdrant
- Lane: Rust service via offline vector bake-off.
- Use: evaluate filtered vector search, quantization, and payload filtering outside live request paths.
- Avoid: bypass search_index.api or become a correctness dependency.
- Pair: pgvector, LanceDB, OpenDAL.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 027. Tantivy
- Lane: Rust via search_index full-text candidate.
- Use: benchmark embedded Rust full-text indexing without a JVM search server.
- Avoid: replace Postgres metadata ownership or skip schema contracts.
- Pair: BM25, tokenizers, Oxc.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 028. Quickwit
- Lane: Rust service via observability and immutable log search optional.
- Use: search large append-only event archives and trace-like data if the observability stack needs it.
- Avoid: serve live content ranking.
- Pair: Tantivy, OpenTelemetry, Parquet.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 029. Meilisearch
- Lane: Rust service via admin search comparison.
- Use: test typo-tolerant admin search UX for noob-friendly panels.
- Avoid: own internal-link ranking.
- Pair: Tantivy, Playwright, GUI tests.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 030. Typesense
- Lane: C++ service via admin search comparison.
- Use: benchmark simple typo-tolerant search for settings and evidence screens.
- Avoid: add another production ranking engine.
- Pair: Meilisearch, Tantivy, pgvector.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 031. Bleve
- Lane: Go via Go service search candidate.
- Use: build small Go-owned searchable indexes inside worker services where a full Rust engine is not justified.
- Avoid: own canonical content search.
- Pair: Go services, ConnectRPC.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 032. Xapian
- Lane: C++ via full-text baseline.
- Use: compare mature C++ probabilistic search behavior with Tantivy and Postgres FTS.
- Avoid: introduce duplicate live search paths.
- Pair: Tantivy, BM25, golden fixtures.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 033. ParadeDB
- Lane: Postgres extension via search_index optional.
- Use: evaluate Postgres-native full-text and vector features only if it fits the no-JVM rule and owner API.
- Avoid: skip module contracts because it lives in Postgres.
- Pair: pgvector, schema_registry.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 034. PGroonga
- Lane: Postgres extension via search_index optional.
- Use: test multilingual full-text behavior inside Postgres for content that PostgreSQL FTS handles poorly.
- Avoid: replace typed feature extraction.
- Pair: pgvector, ICU, MeCab if approved.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 035. pg_trgm
- Lane: Postgres extension via search_index.
- Use: support trigram similarity for admin repair, duplicate title hints, and typo-tolerant lookups.
- Avoid: rank internal-link candidates alone.
- Pair: Postgres FTS, Tantivy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 036. ripgrep
- Lane: Rust tool via developer tooling.
- Use: give agents fast repository search during audits and generated slice execution.
- Avoid: be parsed as a correctness proof.
- Pair: Tree-sitter, Semgrep.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 037. BurntSushi regex
- Lane: Rust via Rust tools.
- Use: use fast deterministic regular expressions in Rust scanners and audit tools.
- Avoid: parse languages with regex where Tree-sitter is required.
- Pair: ripgrep, Tree-sitter.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 038. RE2
- Lane: C++/Go via ingest and scanner paths.
- Use: use safe linear-time regex for user-provided patterns or high-volume matching.
- Avoid: use PCRE-style catastrophic backtracking in hot paths.
- Pair: Hyperscan, Aho-Corasick.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### C. Text, NLP, and extraction

#### 039. fastText
- Lane: C++ via text evidence.
- Use: keep mature language and text-classification callers where they have real approved use.
- Avoid: hide a Python fallback when the library is missing.
- Pair: KenLM, SentencePiece.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 040. KenLM
- Lane: C++ via text quality diagnostics.
- Use: score language-model features for offline text-quality and anchor diagnostics.
- Avoid: run as a live governance decision.
- Pair: fastText, ranking_training.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 041. SentencePiece
- Lane: C++ via tokenization experiments.
- Use: provide deterministic subword tokenization for offline text and embedding diagnostics.
- Avoid: replace Bedrock provider contracts.
- Pair: Tokenizers, KenLM.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 042. Hugging Face Tokenizers
- Lane: Rust/Python via offline tokenizer bank.
- Use: benchmark fast tokenization for approved offline providers and reports.
- Avoid: add local embedding models that the plan deleted.
- Pair: SentencePiece, simdutf.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 043. ICU4C
- Lane: C/C++ via text normalization.
- Use: perform robust Unicode normalization, segmentation, collation, and locale-sensitive text handling.
- Avoid: let locale behavior differ silently between languages.
- Pair: simdutf, ftfy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 044. simdutf
- Lane: C++ via ingest and native text kernels.
- Use: validate and transcode UTF-8 at high speed before indexing, tokenization, or native parsing.
- Avoid: silently repair text without recording normalization.
- Pair: ICU4C, simdjson.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 045. Bling Fire
- Lane: C++ via text segmentation candidate.
- Use: benchmark fast sentence and word segmentation for content extraction and snippets.
- Avoid: own editorial policy or quality decisions.
- Pair: pysbd, SentencePiece.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 046. pysbd
- Lane: Python via text segmentation library.
- Use: keep mature sentence-boundary behavior where approved, while deleting silent degraded fallback.
- Avoid: become a hidden fallback for C++ segmentation.
- Pair: Bling Fire, tests.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 047. VADER
- Lane: Python via offline sentiment features.
- Use: keep simple sentiment evidence for reports where it has tests and provenance.
- Avoid: drive ranking by itself.
- Pair: YAKE, ranking_evidence.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 048. YAKE
- Lane: Python via offline keyword extraction.
- Use: extract unsupervised keywords for evidence and content opportunity drafts.
- Avoid: stuff keywords into generated content or live rankers.
- Pair: RAKE, KeyBERT alternatives only if approved.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 049. RAKE-NLTK
- Lane: Python via keyword extraction baseline.
- Use: provide a simple keyword extraction baseline for content opportunity reports.
- Avoid: run in live scoring.
- Pair: YAKE, GSC evidence.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 050. ftfy
- Lane: Python via ingest cleanup.
- Use: repair mojibake and broken Unicode in offline imports with recorded before/after evidence.
- Avoid: silently mutate canonical content.
- Pair: ICU4C, simdutf.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 051. unicodedata2
- Lane: Python via normalization compatibility.
- Use: standardize Unicode-version behavior in offline Python scripts.
- Avoid: diverge from native normalization without tests.
- Pair: ICU4C, ftfy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 052. uchardet
- Lane: C/C++ via crawler import.
- Use: detect legacy encodings before conversion when crawler data lacks reliable charset metadata.
- Avoid: guess silently without confidence thresholds.
- Pair: simdutf, ftfy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 053. chardet
- Lane: Python via offline encoding fallback candidate.
- Use: compare encoding detection during import only when native uchardet is not accepted.
- Avoid: ship as a hidden live dependency.
- Pair: uchardet, tests.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 054. jusText
- Lane: Python via crawler extraction baseline.
- Use: remove boilerplate from crawled pages for offline content quality checks.
- Avoid: overwrite canonical HTML or publication text.
- Pair: trafilatura, readability-lxml.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 055. trafilatura
- Lane: Python via content extraction baseline.
- Use: extract main text from crawled documents for evidence and opportunity reports.
- Avoid: replace crawler source-of-truth storage.
- Pair: jusText, readability-lxml.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 056. readability-lxml
- Lane: Python via content extraction baseline.
- Use: compare readable body extraction against trafilatura and jusText for golden pages.
- Avoid: be the only parser for malformed HTML.
- Pair: libxml2, tests.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 057. libxml2
- Lane: C via HTML/XML parsing.
- Use: parse and validate high-volume XML/HTML imports where native parsing is required.
- Avoid: accept unsafe parser options or network fetches.
- Pair: lxml, AFL++.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 058. Gumbo parser
- Lane: C via HTML parser candidate.
- Use: benchmark tolerant HTML parsing for native extraction or link parsing.
- Avoid: replace browser-grade parsing without fixture proof.
- Pair: libxml2, linkparse kernel.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### D. Graph and compressed sets

#### 059. Apache AGE
- Lane: Postgres extension via graph_query.
- Use: store and query graph snapshots inside Postgres for content and link evidence.
- Avoid: replace module-owned APIs or accept unvalidated graph writes.
- Pair: pgvector, PageRank jobs.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 060. Kuzu
- Lane: C++ via offline graph experiments.
- Use: test embedded graph database workflows for large local graph analysis.
- Avoid: become a hidden production graph store.
- Pair: Apache AGE, Parquet.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 061. pgRouting
- Lane: Postgres extension via graph_query optional.
- Use: run route and path algorithms inside Postgres if link graph diagnostics need them.
- Avoid: own ranking policy.
- Pair: Apache AGE, Haskell governance.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 062. SuiteSparse GraphBLAS
- Lane: C via graph_query native candidate.
- Use: run sparse-matrix graph algorithms for PageRank, reachability, and random-walk diagnostics.
- Avoid: serve user requests directly.
- Pair: LAGraph, C++ kernels.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 063. LAGraph
- Lane: C via graph algorithm candidate.
- Use: use GraphBLAS-backed graph algorithms as benchmarked native primitives.
- Avoid: skip algorithm-specific fixtures.
- Pair: SuiteSparse GraphBLAS, NetworKit.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 064. NetworKit
- Lane: C++/Python via graph diagnostics.
- Use: compute large-scale network metrics offline for content graph health.
- Avoid: become a live ranking dependency.
- Pair: Apache AGE, graph_tool.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 065. igraph
- Lane: C/Python/R via graph diagnostics.
- Use: provide a mature baseline for centrality, community, and graph metric checks.
- Avoid: introduce R into the app runtime.
- Pair: NetworKit, rustworkx.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 066. graph-tool
- Lane: C++/Python via graph diagnostics optional.
- Use: run advanced statistical graph analysis offline if installation cost is justified.
- Avoid: block core workflows due to install complexity.
- Pair: NetworKit, metadata_catalog.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 067. rustworkx
- Lane: Rust/Python via graph tooling.
- Use: run fast graph algorithms from Python orchestration without NetworkX bottlenecks.
- Avoid: own active ranking decisions.
- Pair: petgraph, NetworkX.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 068. petgraph
- Lane: Rust via Rust graph tools.
- Use: build deterministic Rust graph algorithms in validators and benchmark contenders.
- Avoid: duplicate Apache AGE ownership.
- Pair: rustworkx, GraphBLAS.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 069. Boost Graph Library
- Lane: C++ via native graph baseline.
- Use: provide mature C++ graph algorithm references for native kernels.
- Avoid: add broad Boost dependency without a specific kernel need.
- Pair: SuiteSparse GraphBLAS, Google Benchmark.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 070. NetworkX
- Lane: Python via offline reference oracle.
- Use: define readable reference outputs for small graph fixtures.
- Avoid: process large production graphs.
- Pair: NetworKit, rustworkx.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 071. GraphBLAS Algorithms
- Lane: Python via offline graph reference.
- Use: express graph algorithms using GraphBLAS semantics for fixture validation.
- Avoid: replace native kernels without benchmark proof.
- Pair: SuiteSparse GraphBLAS, NetworkX.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 072. CRoaring
- Lane: C/C++ via sets and graph filters.
- Use: represent candidate IDs, document sets, and graph neighborhoods with compressed bitmaps.
- Avoid: store canonical facts without provenance.
- Pair: RoaringBitmap Go, ranking_runtime.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 073. RoaringBitmap Go
- Lane: Go via Go workers.
- Use: apply the same compressed bitmap model inside Go task and routing workers.
- Avoid: serialize incompatible bitmap formats without version tests.
- Pair: CRoaring, Go services.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 074. EWAHBoolArray
- Lane: Java/C++ concepts via design reference only.
- Use: study compressed bitmap tradeoffs if Roaring performs poorly.
- Avoid: add JVM runtime code.
- Pair: CRoaring, benchmark reports.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 075. MinHashLSH Forest
- Lane: Algorithm pattern via duplicate detection.
- Use: guide LSH index shape for near-duplicate pages and issues.
- Avoid: implement without source-backed spec and precision floor.
- Pair: Broder MinHash, Rust/C++ bake-off.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 076. HyperLogLog
- Lane: Algorithm/library via cardinality estimates.
- Use: estimate unique anchors, queries, and paths cheaply in reports.
- Avoid: make exact quota decisions.
- Pair: Redis, PostgreSQL aggregates.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### E. Ranking and ML quality

#### 077. LightGBM
- Lane: C++/Python via ranking_training.
- Use: train LambdaMART-style ranking candidates and export runtime-compatible artifacts.
- Avoid: activate profiles without Haskell governance.
- Pair: Optuna, SHAP, ranking_runtime.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 078. CatBoost
- Lane: C++/Python via ranking_training.
- Use: train robust ranking candidates and compare against LightGBM on governed offline datasets.
- Avoid: serve live scoring directly from Python.
- Pair: Optuna, metadata_catalog.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 079. XGBoost
- Lane: C++/Python via ranking_training baseline.
- Use: provide a mature boosted-tree baseline for tabular ranking and classification diagnostics.
- Avoid: expand default training cost without evidence.
- Pair: LightGBM, CatBoost.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 080. Optuna
- Lane: Python via ranking_training.
- Use: tune thresholds, weights, and candidate models with persisted studies and pruning.
- Avoid: choose active profiles by itself.
- Pair: LightGBM, CatBoost, SQLite/Postgres storage.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 081. FLAML
- Lane: Python via ranking_training optional AutoML.
- Use: run cost-aware AutoML experiments under strict offline resource budgets.
- Avoid: become required for every training cycle.
- Pair: Optuna, AutoGluon.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 082. AutoGluon
- Lane: Python via ranking_training optional.
- Use: generate candidate models when the Dell or helpers have enough budget.
- Avoid: skip registry approval or runtime compatibility.
- Pair: MLflow mirror, metadata_catalog.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 083. Ray Tune
- Lane: Python via helper execution optional.
- Use: distribute offline tuning trials across helper PCs with deterministic manifests.
- Avoid: own truth or promotion decisions.
- Pair: Optuna, work_routing.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 084. Nevergrad
- Lane: Python via optimization experiments.
- Use: try derivative-free optimization for weights and constraints when Optuna is a poor fit.
- Avoid: replace primary tuning flow without evidence.
- Pair: Optuna, CVXPY.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 085. Hyperopt
- Lane: Python via legacy tuning comparison.
- Use: support old Bayesian optimization experiments only when migration evidence requires it.
- Avoid: start new primary workflows.
- Pair: Optuna, metadata_catalog.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 086. scikit-learn
- Lane: Python/C via offline baselines.
- Use: train simple baselines, calibration models, and diagnostic classifiers.
- Avoid: score live requests.
- Pair: skops, ONNX Runtime.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 087. ONNX Runtime
- Lane: C++/Python via ranking_runtime compatibility candidate.
- Use: evaluate portable model inference for approved exported models.
- Avoid: load arbitrary models without schema and governance.
- Pair: skl2onnx, Treelite.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 088. Treelite
- Lane: C++/Python via tree model export.
- Use: compile tree ensembles for fast native inference when LightGBM or XGBoost wins.
- Avoid: bypass C++ score breakdown contracts.
- Pair: LightGBM, XGBoost.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 089. m2cgen
- Lane: Python via model export reference.
- Use: generate readable model code for tiny baselines or audit comparison.
- Avoid: generate large opaque production scorers.
- Pair: scikit-learn, golden fixtures.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 090. skops
- Lane: Python via model persistence audit.
- Use: store and inspect scikit-learn models safely in offline experiments.
- Avoid: replace artifact hashes and provenance.
- Pair: scikit-learn, metadata_catalog.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 091. SHAP
- Lane: Python/C++ via ranking reports.
- Use: explain candidate model behavior in noob-readable offline reports.
- Avoid: replace deterministic score breakdowns.
- Pair: LightGBM, CatBoost.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 092. Evidently
- Lane: Python via ranking_evidence reports.
- Use: report drift, missingness, and data quality signals before trusting training data.
- Avoid: block or approve production alone.
- Pair: Great Expectations, whylogs.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 093. Great Expectations
- Lane: Python via data quality checks.
- Use: validate incoming evidence datasets with explicit expectations and visible failures.
- Avoid: auto-repair data silently.
- Pair: DuckDB, Parquet.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 094. Deepchecks
- Lane: Python via ML quality diagnostics.
- Use: audit train/test leakage, drift, and model quality in offline reports.
- Avoid: own promotion gates.
- Pair: Evidently, Great Expectations.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 095. whylogs
- Lane: Python via data profiling.
- Use: profile large datasets compactly and compare evidence windows.
- Avoid: store raw private labels when profiles suffice.
- Pair: Evidently, metadata_catalog.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 096. NannyML
- Lane: Python via performance drift optional.
- Use: estimate post-deployment performance drift where labels arrive late.
- Avoid: override human review evidence.
- Pair: Evidently, ranking_evidence.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 097. Alibi Explain
- Lane: Python via explanation experiments.
- Use: produce offline model explanations for candidate reports.
- Avoid: serve runtime explanations.
- Pair: SHAP, report generator.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 098. EconML
- Lane: Python via causal diagnostics optional.
- Use: explore causal treatment effects for content experiments when enough evidence exists.
- Avoid: claim causality from weak observational data.
- Pair: DoWhy, interleaving tests.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### F. Optimization and formal methods

#### 099. Z3
- Lane: C++/Python/Haskell bindings via ranking_governance diagnostics.
- Use: solve SMT constraints for proof obligations, stale evidence checks, and promotion blockers.
- Avoid: activate profiles or replace Haskell verdict code.
- Pair: Haskell governance, SMT-LIB.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 100. cvc5
- Lane: C++/Python via formal-methods comparison.
- Use: cross-check SMT behavior when Z3 results need an independent solver.
- Avoid: double maintenance without disputed cases.
- Pair: Z3, SMT-LIB fixtures.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 101. OR-Tools
- Lane: C++/Python via ranking_training optimization.
- Use: solve assignment, routing, scheduling, and constrained selection problems offline.
- Avoid: hide infeasible constraints from the GUI.
- Pair: CVXPY, Optuna.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 102. CVXPY
- Lane: Python via ranking_training diagnostics.
- Use: model convex optimization problems for weight constraints and budgeted recommendations.
- Avoid: ship solvers in live request paths.
- Pair: OSQP, SCS, HiGHS.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 103. OSQP
- Lane: C/Python via optimization solver.
- Use: solve quadratic programs behind CVXPY where it is the best fit.
- Avoid: select profiles without governance.
- Pair: CVXPY, benchmark reports.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 104. HiGHS
- Lane: C++/Python via linear optimization.
- Use: solve LP and MILP-style offline allocation checks where license and fit allow.
- Avoid: become a hidden scheduler.
- Pair: OR-Tools, CVXPY.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 105. SCIP
- Lane: C/C++ via optimization comparison.
- Use: test hard combinatorial optimization only after license and complexity review.
- Avoid: enter the default install path.
- Pair: OR-Tools, HiGHS.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 106. SymPy
- Lane: Python via symbolic diagnostics.
- Use: derive formulas, simplify constraints, and generate readable math reports offline.
- Avoid: emit production weights directly.
- Pair: Z3, CVXPY.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 107. PySMT
- Lane: Python via SMT abstraction.
- Use: abstract multiple solvers for research diagnostics if Z3/cvc5 divergence matters.
- Avoid: hide solver-specific behavior.
- Pair: Z3, cvc5.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 108. Lean
- Lane: Proof assistant via research lane.
- Use: document formal proofs for small critical invariants when Haskell tests are insufficient.
- Avoid: be required for ordinary feature work.
- Pair: Haskell, LiquidHaskell.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 109. LiquidHaskell
- Lane: Haskell via Haskell correctness.
- Use: add refinement checks to critical Haskell governance functions where practical.
- Avoid: block all Haskell work on proof burden.
- Pair: Haskell tests, QuickCheck.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 110. QuickCheck
- Lane: Haskell via Haskell tests.
- Use: generate property tests for governance, ranking invariants, and parser behavior.
- Avoid: replace example-based BDD coverage.
- Pair: Hspec, LiquidHaskell.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 111. Hedgehog
- Lane: Haskell/Rust concepts via property testing.
- Use: write reproducible property tests with integrated shrinking for Haskell or Rust where supported.
- Avoid: duplicate QuickCheck without a need.
- Pair: QuickCheck, proptest.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 112. Kani
- Lane: Rust via Rust verification.
- Use: model-check Rust code that guards unsafe boundaries or critical invariants.
- Avoid: be required for every Rust utility.
- Pair: Miri, cargo-nextest.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 113. CBMC
- Lane: C/C++ via native verification.
- Use: check bounded C/C++ properties for small native boundary functions.
- Avoid: pretend bounded proof covers all production inputs.
- Pair: libFuzzer, clang-tidy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 114. SAW
- Lane: Verification tool via crypto and low-level proof optional.
- Use: verify small low-level routines only if they become security critical.
- Avoid: enter default feature delivery.
- Pair: CBMC, C test fixtures.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### G. Native performance and serialization

#### 115. simdjson
- Lane: C++ via native JSON ingest.
- Use: parse high-volume JSON, NDJSON, and API exports with measured native speed.
- Avoid: accept schema-invalid data.
- Pair: simdutf, schema_registry.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 116. yyjson
- Lane: C via native JSON candidate.
- Use: benchmark fast C JSON parsing against simdjson for small and mutable JSON workloads.
- Avoid: add a second parser without winner proof.
- Pair: simdjson, AFL++.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 117. RapidJSON
- Lane: C++ via JSON baseline.
- Use: use as a compatibility baseline where mature DOM or SAX patterns help tests.
- Avoid: choose it over faster parsers without evidence.
- Pair: simdjson, yyjson.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 118. nlohmann/json
- Lane: C++ via developer-friendly JSON.
- Use: use only in non-hot C++ tests or tooling where readability matters.
- Avoid: enter kernel hot loops.
- Pair: simdjson, RapidJSON.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 119. FlatBuffers
- Lane: C++/Rust/Go via binary contracts candidate.
- Use: test zero-copy-ish typed binary payloads for native bridge contracts.
- Avoid: replace public DTOs without schema_registry approval.
- Pair: Cap'n Proto, Protobuf.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 120. Cap'n Proto
- Lane: C++ via binary RPC/data candidate.
- Use: benchmark fast serialization for internal native boundaries.
- Avoid: introduce a unique protocol per module.
- Pair: FlatBuffers, Protobuf.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 121. Protocol Buffers
- Lane: C++/Go/Rust via Go services and contracts.
- Use: standardize service contracts where Go, Haskell, and Python need typed messages.
- Avoid: generate business logic.
- Pair: ConnectRPC, buf.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 122. MessagePack
- Lane: C/C++/Go/Python via compact binary payloads.
- Use: serialize small internal artifacts where JSON overhead hurts and schemas remain explicit.
- Avoid: use schemaless payloads for critical contracts.
- Pair: schema_registry, Protobuf.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 123. Zstandard
- Lane: C via artifact compression.
- Use: compress datasets, evidence packs, and traces with high ratio and speed.
- Avoid: compress already-small control records.
- Pair: Parquet, metadata_catalog.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 124. LZ4
- Lane: C via fast compression.
- Use: compress temporary spill files and large intermediate artifacts where speed matters more than ratio.
- Avoid: store long-term archives when Zstandard wins.
- Pair: Zstandard, spill manager.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 125. zlib-ng
- Lane: C via compat compression.
- Use: speed up gzip-compatible flows when upstream formats require gzip.
- Avoid: choose gzip for new large artifacts by default.
- Pair: Zstandard, LZ4.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 126. Snappy
- Lane: C++ via block compression baseline.
- Use: compare fast block compression for Parquet or intermediate files.
- Avoid: replace Zstandard without evidence.
- Pair: Parquet, DuckDB.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 127. mimalloc
- Lane: C/C++ via native kernel allocator.
- Use: benchmark allocator improvements for C++ kernels with allocation pressure.
- Avoid: change allocator globally without measurement.
- Pair: Google Benchmark, heaptrack.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 128. jemalloc
- Lane: C/Rust via native service allocator.
- Use: benchmark memory fragmentation and throughput in Rust or C++ services.
- Avoid: mask leaks instead of fixing them.
- Pair: Valgrind, heaptrack.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 129. tcmalloc
- Lane: C++ via allocator benchmark.
- Use: compare allocator behavior for C++ batch processes.
- Avoid: ship unless it wins measured cases.
- Pair: mimalloc, jemalloc.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 130. abseil-cpp
- Lane: C++ via native utility layer.
- Use: use status types, flat hash maps, strings, and time utilities in C++ kernels.
- Avoid: drag in broad dependencies for tiny kernels.
- Pair: Google Benchmark, clang-tidy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 131. Folly
- Lane: C++ via benchmark-only utility bank.
- Use: test F14 maps and high-performance primitives when hash maps dominate profiles.
- Avoid: be the default utility framework.
- Pair: abseil-cpp, parallel-hashmap.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 132. martinus robin-hood-hashing
- Lane: C++ via native maps.
- Use: benchmark fast hash maps in tight C++ kernels.
- Avoid: replace standard maps everywhere.
- Pair: abseil flat_hash_map, Google Benchmark.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 133. parallel-hashmap
- Lane: C++ via native maps.
- Use: test memory-efficient flat and parallel hash maps in native kernels.
- Avoid: introduce data races or unbounded parallelism.
- Pair: abseil-cpp, TSan.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 134. Boost.Container
- Lane: C++ via native containers.
- Use: use stable vector and flat containers when standard containers miss a proven need.
- Avoid: use Boost broadly without a slice-level reason.
- Pair: abseil-cpp, benchmarks.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 135. fmt
- Lane: C++ via native formatting.
- Use: produce safe formatted messages in C++ without manual string handling.
- Avoid: format inside hot loops without benchmark proof.
- Pair: spdlog, diagnostics.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 136. spdlog
- Lane: C++ via native logging.
- Use: emit structured kernel diagnostics where C++ needs local logging.
- Avoid: duplicate OpenTelemetry spans.
- Pair: fmt, Perfetto.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 137. Google Benchmark
- Lane: C++ via native benchmark harness.
- Use: measure C++ kernel speed at small, medium, and large sizes.
- Avoid: replace product tests.
- Pair: Perfetto, heaptrack.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 138. Catch2
- Lane: C++ via native unit tests.
- Use: write readable C++ unit tests for kernels and C-ABI wrappers.
- Avoid: skip fuzzing or sanitizer tests.
- Pair: libFuzzer, clang-tidy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 139. doctest
- Lane: C++ via lightweight native tests.
- Use: test small C++ header-only utilities quickly.
- Avoid: replace broader integration tests.
- Pair: Catch2, GoogleTest.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 140. GoogleTest
- Lane: C++ via native test suites.
- Use: standardize larger C++ test suites and typed tests.
- Avoid: coexist with too many test frameworks in one module.
- Pair: Google Benchmark, sanitizers.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 141. Criterion.rs
- Lane: Rust via Rust benchmarks.
- Use: measure Rust contenders against C++ and Python reference paths.
- Avoid: declare Rust winner without comparable inputs.
- Pair: cargo-nextest, iai-callgrind.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### H. Observability and profiling

#### 142. OpenTelemetry
- Lane: Multi-language via all modules.
- Use: standardize traces, metrics, and logs across Python, Go, Rust, C++, and frontend boundaries.
- Avoid: replace typed error handling.
- Pair: Grafana Alloy, Prometheus.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 143. Prometheus
- Lane: Go/C++/Python clients via observability.
- Use: export counters, gauges, histograms, and health signals for modules and native kernels.
- Avoid: store audit records.
- Pair: Grafana, Alertmanager.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 144. Grafana Alloy
- Lane: Go agent via observability pipeline.
- Use: collect and route OpenTelemetry, Prometheus, logs, and profiling signals on Mint.
- Avoid: become the source of truth for product state.
- Pair: Beyla, Loki, Tempo.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 145. Grafana Beyla
- Lane: eBPF/Go via Mint observability.
- Use: auto-instrument Linux HTTP and gRPC services without code changes during migration.
- Avoid: replace explicit application spans.
- Pair: OpenTelemetry, Alloy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 146. OpenTelemetry eBPF Instrumentation
- Lane: eBPF via Mint observability candidate.
- Use: track the Beyla-to-OpenTelemetry path and test auto-instrumentation where stable.
- Avoid: depend on beta behavior for release gates.
- Pair: Beyla, OTel SDKs.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 147. Perfetto
- Lane: C++ via native tracing.
- Use: record detailed C++ kernel traces and performance evidence.
- Avoid: remain a stub that only satisfies regex hooks.
- Pair: Google Benchmark, Tracy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 148. Tracy Profiler
- Lane: C++ via native profiling optional.
- Use: profile frame-like native workloads and visualize zones during optimization.
- Avoid: replace Perfetto acceptance where Perfetto is required.
- Pair: Perfetto, Google Benchmark.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 149. pprof
- Lane: Go via Go workers.
- Use: profile CPU, heap, goroutines, and contention in Go task runtime and services.
- Avoid: ship endpoints without access controls.
- Pair: Pyroscope, OTel Go.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 150. Pyroscope
- Lane: Multi-language via profiling.
- Use: collect continuous profiling for Go, Python, and selected native paths.
- Avoid: treat profiles as tests.
- Pair: pprof, Grafana.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 151. Speedscope
- Lane: Web tool via profile review.
- Use: view local profiles and flamegraphs in a lightweight browser UI.
- Avoid: become required infrastructure.
- Pair: pprof, Pyroscope.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 152. Valgrind
- Lane: C/C++ via native memory checks.
- Use: find leaks and invalid memory access in native kernels on test inputs.
- Avoid: run as every-commit default when too slow.
- Pair: ASan, heaptrack.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 153. heaptrack
- Lane: C/C++ via native heap profiling.
- Use: identify allocation hot spots and leaks in C++ batch tools.
- Avoid: replace sanitizer coverage.
- Pair: mimalloc, jemalloc.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 154. LLVM Sanitizers
- Lane: C/C++/Rust via native tests.
- Use: run ASan, UBSan, and TSan on C/C++ and compatible Rust boundaries.
- Avoid: ship sanitizer builds as production binaries.
- Pair: libFuzzer, CI gates.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 155. GWP-ASan
- Lane: C/C++ via native memory safety.
- Use: sample heap bugs in C++ kernels and prove real memory-safety wiring.
- Avoid: stay as a no-op stub.
- Pair: Perfetto, health checks.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 156. bcc
- Lane: eBPF/Python/C via Linux diagnostics.
- Use: run one-off kernel and network diagnostics on Mint when Beyla or OTel misses signals.
- Avoid: be required for application correctness.
- Pair: bpftrace, Beyla.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 157. bpftrace
- Lane: eBPF via Linux diagnostics.
- Use: write short observability probes for CPU, filesystem, and network issues.
- Avoid: debug by mutating production behavior.
- Pair: bcc, perf.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### I. Static analysis and testing

#### 158. Tree-sitter
- Lane: C/Rust via deterministic_validation.
- Use: parse many languages into concrete syntax trees for code graphing and validation.
- Avoid: prove semantic correctness alone.
- Pair: Semgrep, Oxc.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 159. tree-sitter-language-pack
- Lane: Rust/Python via parser coverage.
- Use: bundle maintained grammar packages for broad static-analysis coverage.
- Avoid: accept grammar drift without golden tests.
- Pair: Tree-sitter, parser registry.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 160. Oxc
- Lane: Rust via frontend analysis.
- Use: parse, lint, and analyze JavaScript and TypeScript quickly in quality gates.
- Avoid: replace TypeScript type-checking blindly.
- Pair: Biome, TypeScript compiler.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 161. Biome
- Lane: Rust via frontend quality.
- Use: run fast formatting and linting for JS, TS, JSX, CSS, and related frontend files.
- Avoid: silently rewrite code without review.
- Pair: Oxc, Vitest.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 162. Semgrep
- Lane: OCaml/Python tool via static-analysis comparison.
- Use: run source-pattern security and bug rules as an oracle lane.
- Avoid: treat findings as proof without triage.
- Pair: Tree-sitter, CodeQL.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 163. CodeQL
- Lane: Analysis engine via security analysis.
- Use: run deeper query-based analysis for high-risk languages and security checks.
- Avoid: block all development on noisy findings.
- Pair: Semgrep, SARIF.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 164. clang-tidy
- Lane: C++ via C++ static analysis.
- Use: enforce C++ correctness and maintainability rules for native kernels.
- Avoid: replace tests or fuzzing.
- Pair: clang-format, include-what-you-use.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 165. clang-format
- Lane: C++ via C++ formatting.
- Use: make C++ diffs predictable and reduce review noise.
- Avoid: format generated or vendored code blindly.
- Pair: clang-tidy, precommit.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 166. cppcheck
- Lane: C/C++ via native static analysis.
- Use: catch C/C++ defects as an additional static-analysis lane.
- Avoid: duplicate clang-tidy rules without value.
- Pair: clang-tidy, CI.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 167. include-what-you-use
- Lane: C++ via native dependency hygiene.
- Use: reduce compile time and hidden header dependencies in C++ kernels.
- Avoid: churn stable files without a slice goal.
- Pair: clang-tidy, CMake.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 168. Infer
- Lane: C/C++/Objective-C/Java via static analysis optional.
- Use: test advanced bug detection on native and mobile-adjacent code if relevant.
- Avoid: add JVM-dependent workflow to default gates.
- Pair: clang-tidy, cppcheck.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 169. Frama-C
- Lane: C via C verification optional.
- Use: analyze small C shims or critical C functions when formal proof pays.
- Avoid: expand to C++ or default all code.
- Pair: CBMC, ACSL specs.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 170. AFL++
- Lane: C/C++/Rust via native fuzzing.
- Use: fuzz parsers, C-ABI boundaries, and text kernels with coverage guidance.
- Avoid: fuzz without minimization and corpus retention.
- Pair: libFuzzer, sanitizers.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 171. libFuzzer
- Lane: C/C++/Rust via native fuzzing.
- Use: run in-process fuzz targets for native parsers and kernels.
- Avoid: replace property tests.
- Pair: AFL++, ASan.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 172. Honggfuzz
- Lane: C/C++/Rust/Go via fuzzing comparison.
- Use: compare fuzzing effectiveness for native and Go boundaries where AFL++ is awkward.
- Avoid: maintain every fuzzer forever.
- Pair: AFL++, libFuzzer.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 173. cargo-fuzz
- Lane: Rust via Rust fuzzing.
- Use: create libFuzzer-backed Rust fuzz targets for parsers and kernels.
- Avoid: skip corpus minimization.
- Pair: cargo-nextest, AFL++.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 174. cargo-nextest
- Lane: Rust via Rust tests.
- Use: speed and stabilize Rust test execution on Mint and helper PCs.
- Avoid: hide flaky tests by retrying blindly.
- Pair: cargo-mutants, clippy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 175. cargo-mutants
- Lane: Rust via Rust mutation testing.
- Use: prove Rust tests catch logic changes in critical crates.
- Avoid: run on every tiny edit when too slow.
- Pair: cargo-nextest, proptest.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 176. Miri
- Lane: Rust via Rust UB checks.
- Use: catch undefined behavior in unsafe Rust tests.
- Avoid: claim coverage for FFI C behavior.
- Pair: Kani, cargo-fuzz.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 177. proptest
- Lane: Rust via Rust property tests.
- Use: generate structured inputs and invariants for Rust code.
- Avoid: replace fixture-based regression tests.
- Pair: cargo-fuzz, Kani.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 178. quickcheck-rs
- Lane: Rust via Rust property baseline.
- Use: use simpler property tests where proptest is unnecessary.
- Avoid: duplicate proptest in the same module.
- Pair: proptest, cargo-nextest.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 179. go test fuzzing
- Lane: Go via Go fuzzing.
- Use: fuzz Go parsers, API decoders, and worker payload handlers.
- Avoid: fuzz external services directly.
- Pair: go test, staticcheck.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 180. staticcheck
- Lane: Go via Go static analysis.
- Use: catch Go correctness and style defects beyond go vet.
- Avoid: suppress warnings without comments.
- Pair: golangci-lint, go vet.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 181. gosec
- Lane: Go via Go security analysis.
- Use: detect risky Go patterns in workers, HTTP handlers, and file operations.
- Avoid: treat every finding as exploitable without review.
- Pair: govulncheck, staticcheck.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 182. golangci-lint
- Lane: Go via Go lint aggregator.
- Use: run curated Go linters consistently across Go services.
- Avoid: enable every linter without signal review.
- Pair: staticcheck, gosec.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 183. govulncheck
- Lane: Go via Go vulnerability scanning.
- Use: scan Go modules and call paths for known vulnerabilities.
- Avoid: replace dependency pinning.
- Pair: OSV-Scanner, Renovate.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 184. pytest
- Lane: Python via Python tests.
- Use: test Django orchestration, APIs, management commands, and report builders.
- Avoid: test native correctness only through mocks.
- Pair: pytest-xdist, Hypothesis.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 185. pytest-xdist
- Lane: Python via parallel test execution.
- Use: parallelize safe Python tests on Mint and helpers.
- Avoid: parallelize database tests without isolation.
- Pair: pytest, backpressure.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 186. pytest-benchmark
- Lane: Python via Python benchmark baseline.
- Use: capture Python reference timings before native replacement.
- Avoid: declare production performance from microbenchmarks alone.
- Pair: Pyroscope, native benchmarks.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 187. mutmut
- Lane: Python via Python mutation testing.
- Use: test orchestration logic where Python remains the owner.
- Avoid: mutate generated or migration files.
- Pair: pytest, coverage.py.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### J. Security and supply chain

#### 188. Syft
- Lane: Go tool via SBOM.
- Use: generate software bills of materials for Docker images and native artifacts.
- Avoid: replace lockfiles.
- Pair: Grype, Cosign.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 189. Grype
- Lane: Go tool via vulnerability scanning.
- Use: scan SBOMs and images for known vulnerabilities.
- Avoid: block without severity policy.
- Pair: Syft, Trivy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 190. Trivy
- Lane: Go tool via container and dependency scanning.
- Use: scan containers, filesystems, IaC, and dependencies in CI or Mint gates.
- Avoid: duplicate every scanner without triage.
- Pair: Grype, OSV-Scanner.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 191. OSV-Scanner
- Lane: Go tool via dependency vulnerability scanning.
- Use: check lockfiles against OSV advisories across ecosystems.
- Avoid: replace ecosystem-specific tools.
- Pair: pip-audit, cargo-audit.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 192. pip-audit
- Lane: Python via Python dependency audit.
- Use: scan Python dependencies and produce actionable vulnerability reports.
- Avoid: auto-upgrade packages without tests.
- Pair: OSV-Scanner, Renovate.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 193. cargo-audit
- Lane: Rust via Rust advisories.
- Use: scan Rust dependencies for advisory database matches.
- Avoid: replace cargo-deny policy checks.
- Pair: cargo-deny, OSV-Scanner.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 194. cargo-deny
- Lane: Rust via Rust policy.
- Use: enforce Rust license, advisory, duplicate, and source policies.
- Avoid: block accepted exceptions without allowlist process.
- Pair: cargo-audit, licensee.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 195. npm audit
- Lane: Node tool via frontend advisories.
- Use: detect known JS dependency advisories in the chosen package manager flow.
- Avoid: auto-fix without lockfile review.
- Pair: OSV-Scanner, Renovate.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 196. Sigstore Cosign
- Lane: Go tool via artifact signing.
- Use: sign containers and native artifact attestations.
- Avoid: replace source review.
- Pair: SLSA, in-toto.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 197. SLSA provenance
- Lane: Spec/tooling via build provenance.
- Use: record verifiable build provenance for compiled artifacts.
- Avoid: pretend provenance proves correctness.
- Pair: Cosign, in-toto.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 198. in-toto
- Lane: Python/Go via supply-chain attestations.
- Use: model and verify steps in the build and release chain.
- Avoid: turn simple local workflows into ceremony without risk.
- Pair: SLSA, Cosign.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 199. Gitleaks
- Lane: Go tool via secret scanning.
- Use: scan repository history and diffs for committed secrets.
- Avoid: store found secrets in public logs.
- Pair: TruffleHog, detect-secrets.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 200. TruffleHog
- Lane: Go tool via secret scanning.
- Use: detect and verify secrets in Git and filesystem scans.
- Avoid: run network verification without approval.
- Pair: Gitleaks, detect-secrets.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 201. detect-secrets
- Lane: Python via secret baseline.
- Use: maintain reviewed secret-scan baselines for local development.
- Avoid: approve real secrets as false positives casually.
- Pair: Gitleaks, precommit.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 202. OpenSSF Scorecard
- Lane: Go tool via dependency risk.
- Use: assess external repository practices for high-risk new libraries.
- Avoid: choose packages only by score.
- Pair: OSV, license review.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 203. Renovate
- Lane: Bot/tool via dependency update workflow.
- Use: propose controlled dependency updates with grouped rules and test gates.
- Avoid: auto-merge native or security-sensitive updates.
- Pair: SBOM, CI gates.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### K. Go services and queues

#### 204. go-redis
- Lane: Go via operations.task_runtime.
- Use: talk to Redis Streams, locks, and sorted sets from Go workers.
- Avoid: encode domain correctness in Redis scripts without owner API.
- Pair: Redis Streams, Lua scripts.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 205. Redis Streams
- Lane: Redis via operations.task_runtime.
- Use: hold ready work queues with consumer groups, acknowledgements, and pending messages.
- Avoid: store canonical business records.
- Pair: Postgres job ledger, Go taskrunner.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 206. Redis sorted sets
- Lane: Redis via operations.task_runtime.
- Use: hold delayed jobs by due timestamp before promotion into Streams.
- Avoid: replace durable job metadata.
- Pair: Redis Streams, scheduler.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 207. River
- Lane: Go/Postgres via task queue comparison.
- Use: benchmark Postgres-backed jobs for transaction-coupled workloads.
- Avoid: replace Redis Streams without a migration ADR.
- Pair: Postgres ledger, taskrunner.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 208. Asynq
- Lane: Go/Redis via task queue comparison.
- Use: compare mature Redis-backed Go task queue behavior against the custom runner.
- Avoid: import its model blindly.
- Pair: Redis Streams, benchmark harness.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 209. Watermill
- Lane: Go via event plumbing candidate.
- Use: route messages across Redis, SQL, or NATS-like transports when a module needs pluggable Go plumbing.
- Avoid: create a broker abstraction before need.
- Pair: ConnectRPC, NATS.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 210. NATS JetStream
- Lane: Go/service via transport benchmark.
- Use: test replayable messaging where Redis Streams cannot meet requirements.
- Avoid: add another required broker casually.
- Pair: Watermill, backpressure.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 211. ConnectRPC
- Lane: Go/Protobuf/TS via Go API boundaries.
- Use: define simple HTTP-compatible Protobuf APIs for Go services and frontend clients.
- Avoid: make every module remote.
- Pair: buf, Protobuf.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 212. gRPC-Go
- Lane: Go via Go RPC baseline.
- Use: support standard gRPC when streaming or compatibility requires it.
- Avoid: force gRPC for simple local calls.
- Pair: ConnectRPC, grpc-gateway.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 213. grpc-gateway
- Lane: Go via REST compatibility.
- Use: expose HTTP JSON compatibility for gRPC services where needed.
- Avoid: maintain duplicate hand-written APIs.
- Pair: gRPC-Go, OpenAPI.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 214. buf
- Lane: Go/tool via Protobuf governance.
- Use: lint, break-check, and generate Protobuf contracts consistently.
- Avoid: let generated code become the architecture.
- Pair: ConnectRPC, Protobuf.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 215. chi
- Lane: Go via HTTP routing.
- Use: build small Go HTTP services with predictable middleware.
- Avoid: write business logic in handlers.
- Pair: otel-go, zap.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 216. httprouter
- Lane: Go via HTTP routing baseline.
- Use: benchmark minimal router overhead for tiny services.
- Avoid: fragment router choice without ADR.
- Pair: chi, pprof.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 217. zap
- Lane: Go via structured logging.
- Use: emit fast structured logs from Go workers.
- Avoid: hide errors only in logs.
- Pair: zerolog, OpenTelemetry.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 218. zerolog
- Lane: Go via structured logging candidate.
- Use: compare allocation behavior for Go logs when zap is heavy.
- Avoid: use both in one service.
- Pair: zap, pprof.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 219. cobra
- Lane: Go via CLI commands.
- Use: build consistent Go management CLIs for worker diagnostics and repair tools.
- Avoid: create CLIs that bypass Django owner APIs.
- Pair: viper, taskrunner.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### L. Frontend and UX

#### 220. TanStack Query
- Lane: TypeScript via frontend data access.
- Use: cache server state and express loading, blocked, stale, and error states cleanly.
- Avoid: own business truth in the browser.
- Pair: OpenAPI client, MSW.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 221. TanStack Table
- Lane: TypeScript via frontend tables.
- Use: render evidence, library registry, issue, and audit tables with sorting and filtering.
- Avoid: compute governance outcomes.
- Pair: ranking_gui view models.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 222. Zod
- Lane: TypeScript via frontend validation.
- Use: validate form and API boundary shapes in the browser.
- Avoid: replace backend schema_registry validation.
- Pair: React Hook Form, OpenAPI.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 223. Valibot
- Lane: TypeScript via frontend validation candidate.
- Use: benchmark smaller validation bundles against Zod for forms.
- Avoid: use both libraries in one form family.
- Pair: Zod, bundle analysis.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 224. React Hook Form
- Lane: TypeScript via frontend forms.
- Use: build noob-friendly approval and configuration forms with low re-render cost.
- Avoid: store domain state only in form state.
- Pair: Zod, Radix UI.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 225. XState
- Lane: TypeScript via frontend state machines.
- Use: model complex approval, repair, and rollout states explicitly.
- Avoid: replace backend state transitions.
- Pair: TanStack Query, Playwright.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 226. Zustand
- Lane: TypeScript via frontend local state.
- Use: hold small UI-only state where React context gets noisy.
- Avoid: store server truth.
- Pair: TanStack Query, tests.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 227. Jotai
- Lane: TypeScript via frontend local state candidate.
- Use: test atomic UI state for complex panels if Zustand is too broad.
- Avoid: mix many state stores without ADR.
- Pair: Zustand, React tests.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 228. Radix UI
- Lane: TypeScript/React via frontend primitives.
- Use: build accessible dialogs, menus, tabs, and controls without inventing widgets.
- Avoid: ship unstyled primitives without UX review.
- Pair: axe-core, shadcn/ui.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 229. shadcn/ui
- Lane: TypeScript/React via frontend component layer.
- Use: compose noob-friendly screens quickly from accessible Tailwind components.
- Avoid: let UI components compute product rules.
- Pair: Radix UI, Storybook.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### M. Haskell validation

#### 230. Megaparsec
- Lane: Haskell via deterministic_validation.
- Use: build total parsers for policy DSLs, manifests, and reason-code formats.
- Avoid: parse general programming languages already covered by Tree-sitter.
- Pair: Hspec, QuickCheck.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 231. Attoparsec
- Lane: Haskell via Haskell parsing hot paths.
- Use: parse simple high-volume byte streams where speed beats Megaparsec error messages.
- Avoid: use for user-facing DSL errors.
- Pair: Megaparsec, benchmarks.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 232. Aeson
- Lane: Haskell via Haskell JSON.
- Use: encode and decode governance inputs and outputs with explicit types.
- Avoid: accept unknown fields without policy.
- Pair: schema_registry, golden JSON.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 233. Servant
- Lane: Haskell via Haskell API optional.
- Use: expose typed Haskell service APIs if governance runs out-of-process.
- Avoid: move Go plumbing into Haskell.
- Pair: Protobuf, ConnectRPC.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 234. Hspec
- Lane: Haskell via Haskell tests.
- Use: write readable unit and behavior tests for Haskell governance.
- Avoid: replace property tests.
- Pair: QuickCheck, Hedgehog.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 235. criterion
- Lane: Haskell via Haskell benchmarks.
- Use: measure Haskell pure-core performance when governance code gets hot.
- Avoid: compare against C++ without equivalent inputs.
- Pair: Hspec, profiling.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 236. weeder
- Lane: Haskell via dead code checks.
- Use: find unused Haskell exports and modules.
- Avoid: delete code without owner review.
- Pair: HLS, Cabal tests.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 237. hlint
- Lane: Haskell via Haskell lint.
- Use: catch simple Haskell style and correctness suggestions.
- Avoid: apply hints blindly.
- Pair: ormolu, tests.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 238. ormolu
- Lane: Haskell via Haskell formatting.
- Use: keep Haskell formatting consistent and reviewable.
- Avoid: format generated code without marker.
- Pair: hlint, CI.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 239. fourmolu
- Lane: Haskell via Haskell formatter candidate.
- Use: use only if the repo standard chooses it over ormolu.
- Avoid: run two formatters.
- Pair: ormolu, ADR.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 240. Haskell Language Server
- Lane: Haskell via developer tooling.
- Use: help agents inspect types and errors while editing Haskell.
- Avoid: be a required runtime service.
- Pair: Cabal, ghcid.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 241. ghcid
- Lane: Haskell via fast feedback.
- Use: run fast compile/test feedback loops for Haskell slices.
- Avoid: replace full CI gates.
- Pair: Hspec, Cabal.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

### N. Build and documentation infrastructure

#### 242. CMake
- Lane: C/C++ via native builds.
- Use: build C++ kernels and C-ABI shared libraries reproducibly.
- Avoid: hide generated artifacts outside compiled store.
- Pair: Ninja, clang-tidy.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 243. Ninja
- Lane: C/C++ via native builds.
- Use: speed incremental native builds from CMake.
- Avoid: become a custom build system.
- Pair: CMake, ccache.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 244. ccache
- Lane: C/C++ via build acceleration.
- Use: speed repeated native builds on Mint and helpers.
- Avoid: cache unsafe compiler outputs without key hygiene.
- Pair: CMake, Ninja.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 245. sccache
- Lane: Rust/C/C++ via distributed build cache optional.
- Use: cache Rust and native builds across helper PCs when configured safely.
- Avoid: hide stale build artifacts.
- Pair: ccache, CI checks.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 246. Bazel
- Lane: Polyglot build via distributed build optional.
- Use: coordinate large build and test execution if existing plan standardizes on it.
- Avoid: add for one module only.
- Pair: BuildBuddy, remote cache.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 247. BuildBuddy
- Lane: Bazel ecosystem via remote execution optional.
- Use: run Bazel remote execution, cache, and result UI when Bazel is canonical.
- Avoid: replace language-specific tests.
- Pair: Bazel, helper PCs.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 248. Just
- Lane: Rust tool via developer commands.
- Use: define readable repo commands for repeatable slice execution.
- Avoid: hide business logic in shell recipes.
- Pair: Make, task docs.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 249. Taskfile
- Lane: Go tool via developer commands candidate.
- Use: define cross-platform commands if Just does not fit the team.
- Avoid: maintain duplicate command runners.
- Pair: Just, docs.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 250. pre-commit
- Lane: Python tool via local hooks.
- Use: run formatting, lint, ownership, and no-fallback checks before commits.
- Avoid: replace CI.
- Pair: language hooks, audit scripts.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 251. OpenAPI Generator
- Lane: Tool via API clients.
- Use: generate typed frontend clients from approved API specs.
- Avoid: generate APIs without owner review.
- Pair: MSW, schema_registry.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 252. Spectral
- Lane: Node tool via API linting.
- Use: lint OpenAPI contracts for consistency and breaking changes.
- Avoid: own runtime validation.
- Pair: OpenAPI Generator, schema_registry.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 253. Redocly CLI
- Lane: Node tool via API docs.
- Use: render and validate API documentation for operators and agents.
- Avoid: be the only contract check.
- Pair: Spectral, OpenAPI.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 254. MkDocs Material
- Lane: Python via knowledge base.
- Use: publish the library bank, ADR index, and slice cookbook as navigable docs.
- Avoid: replace source-controlled specs.
- Pair: Mermaid, markdownlint.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 255. mdBook
- Lane: Rust via knowledge base candidate.
- Use: publish Rust-friendly reference docs for agent workflows if MkDocs is too Python-heavy.
- Avoid: run both doc systems.
- Pair: MkDocs, Mermaid.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

#### 256. markdownlint-cli2
- Lane: Node via docs lint.
- Use: keep Markdown specs predictable for agents and review.
- Avoid: rewrite technical meaning.
- Pair: MkDocs, CI.
- Gate: ADR, tests, pin, security, resources, health, no fallback.

## 6. Implementation slices

Each slice is self-contained. Copy one slice into an agent session when you want that work performed. The agent must still inspect the repository before editing files. The slice gives boundaries and acceptance criteria, not permission to guess.

### Slice 001 - Library expansion registry and owner gates

Goal: Create the canonical registry that agents must query before adding a dependency.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-001-library-expansion-registry-and-owner-gates.md` and `docs/prd/slice-001-library-expansion-registry-and-owner-gates.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: docs/specs/fr-approved-library-expansion-bank.md; backend/apps/library_registry/api.py; backend/apps/library_registry/tests/test_registry_contract.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Library expansion registry and owner gates
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Boost Graph Library, TanStack Query. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 002 - License, package, and security intake

Goal: Block unreviewed dependencies before they reach code.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-002-license-package-and-security-intake.md` and `docs/prd/slice-002-license-package-and-security-intake.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/library_registry/security.py; audit/library-license-risk.md; .github/workflows/dependency-risk.yml. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: License, package, and security intake
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Arrow Acero, pgvector, ripgrep, chardet, NetworkX, ONNX Runtime. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 003 - Capability recipe index

Goal: Map recurring tasks to approved library combinations.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-003-capability-recipe-index.md` and `docs/prd/slice-003-capability-recipe-index.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: docs/library-recipes/*.md; backend/apps/library_registry/recipes.py; tests/test_capability_recipes.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Capability recipe index
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Boost Graph Library. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 004 - Language ownership enforcement

Goal: Prevent agents from placing work in the wrong language.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-004-language-ownership-enforcement.md` and `docs/prd/slice-004-language-ownership-enforcement.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: .githooks/check-language-ownership.py; docs/LANGUAGE-OWNERSHIP.md; tests/test_language_ownership.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Language ownership enforcement
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: tree-sitter-language-pack, Haskell Language Server. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 005 - No-fallback scanner

Goal: Detect and reject fallback branches that hide missing native artifacts.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-005-no-fallback-scanner.md` and `docs/prd/slice-005-no-fallback-scanner.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: .githooks/check-no-fallback.py; backend/apps/diagnostics/tests/test_no_fallback_scan.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: No-fallback scanner
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: OSV-Scanner, detect-secrets. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 006 - Benchmark harness standard

Goal: Standardize small, medium, and large benchmark evidence.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-006-benchmark-harness-standard.md` and `docs/prd/slice-006-benchmark-harness-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/perf_baselines/api.py; docs/specs/fr-benchmark-standard.md; tests/test_perf_baseline_contract.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Benchmark harness standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, Google Benchmark, pytest-benchmark. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 007 - Native artifact health registry

Goal: Make missing compiled artifacts fail loudly.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-007-native-artifact-health-registry.md` and `docs/prd/slice-007-native-artifact-health-registry.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/diagnostics/health.py; scripts/ensure_compiled_artifacts.py; tests/test_native_artifact_health.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Native artifact health registry
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Substrait, NGT, SentencePiece, Gumbo parser, MinHashLSH Forest, Evidently. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 008 - Dependency graph dashboard

Goal: Show which module owns each library and which libraries remain candidates.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-008-dependency-graph-dashboard.md` and `docs/prd/slice-008-dependency-graph-dashboard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/library_registry/selectors.py; frontend/src/app/library-registry/*; tests/libraryRegistry.test.ts. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Dependency graph dashboard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: SuiteSparse GraphBLAS, LAGraph, igraph, graph-tool, petgraph, Boost Graph Library, GraphBLAS Algorithms. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 009 - Parser foundation

Goal: Adopt Tree-sitter and Oxc for code intelligence without regex parsers.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-009-parser-foundation.md` and `docs/prd/slice-009-parser-foundation.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/deterministic_validation/parsers/*; services/parserd/*; tests/parser_fixtures/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Parser foundation
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: BurntSushi regex, Gumbo parser, Tree-sitter, tree-sitter-language-pack. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 010 - Frontend quality gate

Goal: Wire Biome, Vitest, Playwright, MSW, and axe-core to prove UI truth states.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-010-frontend-quality-gate.md` and `docs/prd/slice-010-frontend-quality-gate.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: frontend/biome.json; frontend/tests/*; .github/workflows/frontend-quality.yml. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Frontend quality gate
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Biome, SLSA provenance. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 011 - Native JSON and Unicode ingest

Goal: Use simdjson and simdutf for high-volume imports.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-011-native-json-and-unicode-ingest.md` and `docs/prd/slice-011-native-json-and-unicode-ingest.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/extensions/json_ingest.cpp; docs/specs/fr-native-json-ingest.md; tests/test_json_ingest_native.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Native JSON and Unicode ingest
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: simdutf, unicodedata2, simdjson. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 012 - Text extraction comparison lane

Goal: Compare trafilatura, jusText, readability-lxml, libxml2, and Gumbo on golden pages.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-012-text-extraction-comparison-lane.md` and `docs/prd/slice-012-text-extraction-comparison-lane.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/content_extraction/*; tests/fixtures/golden_pages/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Text extraction comparison lane
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: jusText, trafilatura, readability-lxml, libxml2, Gumbo parser. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 013 - Fingerprint and hash standard

Goal: Choose BLAKE3, XXH3, MinHash, SimHash, and canonical fingerprint roles.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-013-fingerprint-and-hash-standard.md` and `docs/prd/slice-013-fingerprint-and-hash-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/fingerprints/api.py; backend/extensions/fingerprint.cpp; tests/test_fingerprint_contract.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Fingerprint and hash standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: MinHashLSH Forest, Zstandard. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 014 - Compressed candidate set standard

Goal: Use CRoaring and RoaringBitmap Go for candidate and graph sets.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-014-compressed-candidate-set-standard.md` and `docs/prd/slice-014-compressed-candidate-set-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/extensions/bitmap_sets.cpp; services/taskrunner/internal/bitsets/*; tests/test_bitmap_sets.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Compressed candidate set standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: SuiteSparse GraphBLAS, LAGraph, igraph, graph-tool, petgraph, Boost Graph Library, GraphBLAS Algorithms, CRoaring. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 015 - pgvector live retrieval contract

Goal: Lock live Stage 1 retrieval behind search_index.api and pgvector HNSW.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-015-pgvector-live-retrieval-contract.md` and `docs/prd/slice-015-pgvector-live-retrieval-contract.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/search_index/api.py; migrations/*pgvector_hnsw*; tests/test_stage1_pgvector.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: pgvector live retrieval contract
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: pgvector, USearch, Meilisearch. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 016 - Vector search bake-off harness

Goal: Compare USearch, hnswlib, LanceDB, Qdrant, FAISS, DiskANN, and NGT offline.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-016-vector-search-bake-off-harness.md` and `docs/prd/slice-016-vector-search-bake-off-harness.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/search_index/benchmarks/vector_bakeoff.py; audit/vector-bakeoff.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Vector search bake-off harness
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: LanceDB, pgvector, USearch, hnswlib, FAISS, DiskANN, Qdrant, Meilisearch. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 017 - Full-text search bake-off harness

Goal: Compare Tantivy, Postgres FTS, PGroonga, ParadeDB, Xapian, and admin search tools.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-017-full-text-search-bake-off-harness.md` and `docs/prd/slice-017-full-text-search-bake-off-harness.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/search_index/benchmarks/fulltext_bakeoff.py; audit/fulltext-bakeoff.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Full-text search bake-off harness
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: USearch, Tantivy, Meilisearch, Xapian, ParadeDB, PGroonga. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 018 - Retrieval fusion contract

Goal: Apply RRF and typed retrieval evidence without creating a hidden ranker.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-018-retrieval-fusion-contract.md` and `docs/prd/slice-018-retrieval-fusion-contract.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_runtime/fusion/*; docs/specs/fr-retrieval-fusion.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Retrieval fusion contract
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Apache DataFusion. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 019 - Graph snapshot source of truth

Goal: Store link graph snapshots through graph_query.api and provenance.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-019-graph-snapshot-source-of-truth.md` and `docs/prd/slice-019-graph-snapshot-source-of-truth.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/graph_query/*; backend/apps/provenance/*; tests/test_graph_snapshot_contract.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Graph snapshot source of truth
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: SuiteSparse GraphBLAS, LAGraph, igraph, graph-tool, petgraph, Boost Graph Library, GraphBLAS Algorithms, Sigstore Cosign. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 020 - Graph diagnostics bank

Goal: Wire AGE, NetworKit, igraph, GraphBLAS, rustworkx, and NetworkX as scoped diagnostics.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-020-graph-diagnostics-bank.md` and `docs/prd/slice-020-graph-diagnostics-bank.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/graph_query/diagnostics/*; audit/graph-diagnostics.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Graph diagnostics bank
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: SuiteSparse GraphBLAS, LAGraph, NetworKit, igraph, graph-tool, rustworkx, petgraph, Boost Graph Library. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 021 - Random-walk and authority metrics

Goal: Implement PageRank, HITS, random walks, DeepWalk, and node2vec diagnostics as evidence.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-021-random-walk-and-authority-metrics.md` and `docs/prd/slice-021-random-walk-and-authority-metrics.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/graph_query/authority/*; tests/test_authority_metrics.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Random-walk and authority metrics
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: hnswlib, RE2, trafilatura, CRoaring, m2cgen, SymPy. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 022 - Feature-row columnar pipeline

Goal: Use Arrow, Parquet, DuckDB, Polars, and DataFusion for feature generation.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-022-feature-row-columnar-pipeline.md` and `docs/prd/slice-022-feature-row-columnar-pipeline.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_features/*; backend/apps/ranking_training/datasets/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Feature-row columnar pipeline
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Apache Arrow, Arrow Acero, Apache Parquet, DuckDB, Polars, Apache DataFusion. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 023 - Dataset version and artifact store

Goal: Use metadata_catalog with Parquet, OpenDAL, delta-rs, Lance, and BLAKE3 hashes.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-023-dataset-version-and-artifact-store.md` and `docs/prd/slice-023-dataset-version-and-artifact-store.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/metadata_catalog/*; tests/test_artifact_store.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Dataset version and artifact store
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Apache Parquet, delta-rs, OpenDAL, Lance format, LanceDB, Sigstore Cosign. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 024 - Data quality gate

Goal: Validate evidence with Great Expectations-style checks and typed quarantine.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-024-data-quality-gate.md` and `docs/prd/slice-024-data-quality-gate.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_evidence/quality/*; tests/test_data_quality_gate.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Data quality gate
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Great Expectations, Deepchecks. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 025 - Drift and profile monitoring

Goal: Use Evidently, whylogs, Deepchecks, and NannyML for offline reports.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-025-drift-and-profile-monitoring.md` and `docs/prd/slice-025-drift-and-profile-monitoring.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_evidence/drift/*; reports/drift/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Drift and profile monitoring
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Evidently, Deepchecks, whylogs, NannyML, Tracy Profiler. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 026 - Offline ranker candidate registry

Goal: Register LightGBM, CatBoost, XGBoost, scikit-learn, and AutoGluon candidates.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-026-offline-ranker-candidate-registry.md` and `docs/prd/slice-026-offline-ranker-candidate-registry.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_training/model_registry.py; tests/test_model_candidate_registry.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Offline ranker candidate registry
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: LightGBM, CatBoost, XGBoost, AutoGluon, scikit-learn. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 027 - Hyperparameter search and budget control

Goal: Use Optuna, FLAML, Ray Tune, Nevergrad, and Hyperopt only through budgets.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-027-hyperparameter-search-and-budget-control.md` and `docs/prd/slice-027-hyperparameter-search-and-budget-control.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_training/tuning/*; tests/test_tuning_budget.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Hyperparameter search and budget control
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: USearch, Meilisearch, Optuna, FLAML, Nevergrad, Hyperopt. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 028 - Model export compatibility

Goal: Evaluate ONNX Runtime, Treelite, m2cgen, and native scoring compatibility.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-028-model-export-compatibility.md` and `docs/prd/slice-028-model-export-compatibility.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_runtime/model_export/*; tests/test_model_export_compat.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Model export compatibility
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: ONNX Runtime, Treelite, m2cgen. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 029 - Explanation report lane

Goal: Use SHAP, Alibi, and deterministic score breakdowns in reports.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-029-explanation-report-lane.md` and `docs/prd/slice-029-explanation-report-lane.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_evidence/reports/explanations.py; tests/test_explanation_reports.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Explanation report lane
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Alibi Explain, OpenSSF Scorecard. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 030 - Optimization and solver diagnostics

Goal: Wire Z3, cvc5, OR-Tools, CVXPY, OSQP, HiGHS, SCIP, and SymPy as offline diagnostics.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-030-optimization-and-solver-diagnostics.md` and `docs/prd/slice-030-optimization-and-solver-diagnostics.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_training/diagnostics/solvers/*; tests/test_solver_diagnostics.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Optimization and solver diagnostics
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: OR-Tools, CVXPY, HiGHS, SymPy. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 031 - Haskell governance interface

Goal: Route correctness, promotion, and invariants to Haskell only.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-031-haskell-governance-interface.md` and `docs/prd/slice-031-haskell-governance-interface.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/ranking_governance/*; haskell/governance/*; tests/test_governance_boundary.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Haskell governance interface
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: LiquidHaskell, httprouter, Haskell Language Server. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 032 - C++ kernel standard

Goal: Require C-ABI, no exceptions, benchmark proof, Perfetto, GWP-ASan, and sanitizer tests.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-032-c++-kernel-standard.md` and `docs/prd/slice-032-c++-kernel-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: docs/specs/fr-cpp-kernel-standard.md; backend/extensions/*; tests/native/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: C++ kernel standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, Google Benchmark, Perfetto, LLVM Sanitizers, GWP-ASan, pytest-benchmark. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 033 - Rust contender standard

Goal: Require Rust contenders to prove speed and memory before replacing C++ or Python.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-033-rust-contender-standard.md` and `docs/prd/slice-033-rust-contender-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: services/rust_hotpaths/*; audit/language-choice-proof/*; tests/rust/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Rust contender standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, Speedscope, SLSA provenance. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 034 - Allocator and container bake-off

Goal: Compare mimalloc, jemalloc, tcmalloc, abseil, Folly, robin-map, and parallel-hashmap only under profile evidence.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-034-allocator-and-container-bake-off.md` and `docs/prd/slice-034-allocator-and-container-bake-off.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/extensions/benchmarks/allocator_bakeoff.cpp; audit/allocator-bakeoff.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Allocator and container bake-off
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: mimalloc, jemalloc, tcmalloc, abseil-cpp, Folly, parallel-hashmap, Boost.Container, Tracy Profiler. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 035 - Serialization format decision lane

Goal: Compare JSON, Protobuf, FlatBuffers, Cap'n Proto, MessagePack, and Parquet by boundary.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-035-serialization-format-decision-lane.md` and `docs/prd/slice-035-serialization-format-decision-lane.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: docs/specs/fr-serialization-boundaries.md; tests/test_serialization_boundaries.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Serialization format decision lane
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Apache Parquet, Lance format, FlatBuffers, Cap'n Proto, Protocol Buffers, MessagePack, clang-format. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 036 - Compression and spill policy

Goal: Use Zstandard, LZ4, zlib-ng, Snappy, and spill directories under disk budgets.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-036-compression-and-spill-policy.md` and `docs/prd/slice-036-compression-and-spill-policy.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/metadata_catalog/compression.py; tests/test_spill_policy.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Compression and spill policy
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, zlib-ng, Snappy. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 037 - Go task runtime queue proof

Goal: Compare Redis Streams, Redis sorted sets, River, Asynq, Watermill, and NATS JetStream.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-037-go-task-runtime-queue-proof.md` and `docs/prd/slice-037-go-task-runtime-queue-proof.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: services/taskrunner/*; benchmarks/task_runtime/*; audit/task-queue-bakeoff.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Go task runtime queue proof
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: ONNX Runtime, go-redis, Redis Streams, Redis sorted sets, River, Asynq, Watermill. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 038 - Go API boundary standard

Goal: Use ConnectRPC, gRPC-Go, grpc-gateway, buf, chi, and OpenTelemetry Go correctly.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-038-go-api-boundary-standard.md` and `docs/prd/slice-038-go-api-boundary-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: services/*/api/*; proto/*; tests/go_api_boundary/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Go API boundary standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, OpenTelemetry, OpenTelemetry eBPF Instrumentation, ConnectRPC, gRPC-Go, grpc-gateway. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 039 - Lua sandbox and policy overlays

Goal: Use go-lua style bounded policies and block correctness logic in Lua.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-039-lua-sandbox-and-policy-overlays.md` and `docs/prd/slice-039-lua-sandbox-and-policy-overlays.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: internal/lua/*; policies/examples/*; tests/lua_policy/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Lua sandbox and policy overlays
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: fastText, readability-lxml, RoaringBitmap Go, skops, PySMT, LZ4. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 040 - Frontend state and forms standard

Goal: Use TanStack Query, Table, Zod or Valibot, React Hook Form, XState, Zustand or Jotai.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-040-frontend-state-and-forms-standard.md` and `docs/prd/slice-040-frontend-state-and-forms-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: frontend/src/app/*; frontend/tests/stateForms.test.ts. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Frontend state and forms standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, TanStack Query, TanStack Table, Valibot, React Hook Form, XState, Zustand. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 041 - Frontend component and docs standard

Goal: Use Radix UI, shadcn/ui, Monaco, Mermaid, Storybook, and accessibility checks.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-041-frontend-component-and-docs-standard.md` and `docs/prd/slice-041-frontend-component-and-docs-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: frontend/src/components/*; .storybook/*; tests/a11y/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Frontend component and docs standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, Radix UI, shadcn/ui. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 042 - Static-analysis detector bank

Goal: Use Semgrep, CodeQL, clang-tidy, cppcheck, Infer, Frama-C, staticcheck, gosec, and govulncheck as scoped lanes.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-042-static-analysis-detector-bank.md` and `docs/prd/slice-042-static-analysis-detector-bank.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/findbugs/*; rules/static_analysis/*; audit/static-analysis-bank.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Static-analysis detector bank
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Semgrep, CodeQL, clang-tidy, cppcheck, Infer, Frama-C, staticcheck, gosec. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 043 - Native fuzzing standard

Goal: Use AFL++, libFuzzer, Honggfuzz, cargo-fuzz, Go fuzzing, sanitizers, and corpus minimization.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-043-native-fuzzing-standard.md` and `docs/prd/slice-043-native-fuzzing-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: fuzz/*; tests/fuzz_corpora/*; docs/specs/fr-fuzzing-standard.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Native fuzzing standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, LLVM Sanitizers, AFL++, libFuzzer, Honggfuzz, cargo-fuzz, go test fuzzing. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 044 - Mutation and property testing standard

Goal: Use cargo-mutants, mutmut, Cosmic Ray, Hypothesis, proptest, QuickCheck, and Hedgehog where each language owns logic.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-044-mutation-and-property-testing-standard.md` and `docs/prd/slice-044-mutation-and-property-testing-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: tests/mutation/*; audit/mutation-gates.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Mutation and property testing standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: QuickCheck, Hedgehog, Zstandard, tree-sitter-language-pack, cargo-mutants, proptest, quickcheck-rs, mutmut. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 045 - Observability and profiling standard

Goal: Use OpenTelemetry, Prometheus, Alloy, Beyla, OBI, pprof, Pyroscope, Tempo, Loki, and Grafana.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-045-observability-and-profiling-standard.md` and `docs/prd/slice-045-observability-and-profiling-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: observability/*; backend/apps/diagnostics/observability.py; tests/test_observability_contract.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Observability and profiling standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, OpenTelemetry, Prometheus, Grafana Alloy, Grafana Beyla, OpenTelemetry eBPF Instrumentation, pprof, Pyroscope. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 046 - C++ memory and trace proof

Goal: Replace Perfetto and GWP-ASan stubs with real instrumentation and visible health checks.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-046-c++-memory-and-trace-proof.md` and `docs/prd/slice-046-c++-memory-and-trace-proof.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/extensions/include/perfetto.h; backend/extensions/include/gwp_asan.h; tests/test_native_observability.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: C++ memory and trace proof
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: OpenTelemetry eBPF Instrumentation, Perfetto, GWP-ASan, bpftrace. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 047 - Supply-chain and SBOM gate

Goal: Use Syft, Grype, Trivy, OSV-Scanner, pip-audit, cargo-audit, cargo-deny, Cosign, SLSA, and in-toto.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-047-supply-chain-and-sbom-gate.md` and `docs/prd/slice-047-supply-chain-and-sbom-gate.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: security/*; .github/workflows/supply-chain.yml; audit/sbom/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Supply-chain and SBOM gate
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Grype, Trivy, OSV-Scanner, pip-audit, cargo-audit, cargo-deny, Sigstore Cosign. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 048 - Secret scanning and dependency updates

Goal: Use Gitleaks, TruffleHog, detect-secrets, Renovate, Dependabot, licensee, Scorecard, and policy files.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-048-secret-scanning-and-dependency-updates.md` and `docs/prd/slice-048-secret-scanning-and-dependency-updates.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: .gitleaks.toml; .secrets.baseline; renovate.json; audit/dependency-updates.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Secret scanning and dependency updates
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Gitleaks, TruffleHog, detect-secrets, OpenSSF Scorecard, Renovate. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 049 - Build and cache standard

Goal: Use CMake, Ninja, ccache, sccache, Bazel, BuildBuddy, Just, Taskfile, and pre-commit without duplicating command ownership.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-049-build-and-cache-standard.md` and `docs/prd/slice-049-build-and-cache-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: build/*; justfile; .pre-commit-config.yaml; docs/build-standard.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Build and cache standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Zstandard, CMake, Ninja, ccache, sccache, Bazel, BuildBuddy, Taskfile. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 050 - API docs and contract generation

Goal: Use OpenAPI Generator, Spectral, Redocly, Protobuf, buf, and schema_registry.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-050-api-docs-and-contract-generation.md` and `docs/prd/slice-050-api-docs-and-contract-generation.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: openapi/*; proto/*; docs/api/*; tests/test_contract_generation.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: API docs and contract generation
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: OpenAPI Generator, Spectral, Redocly CLI. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 051 - Knowledge-base publishing

Goal: Use MkDocs or mdBook, Mermaid, markdownlint, Vale, ADR indexes, and recipe pages.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-051-knowledge-base-publishing.md` and `docs/prd/slice-051-knowledge-base-publishing.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: docs/mkdocs.yml; docs/library-recipes/*; tests/docs/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Knowledge-base publishing
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: MkDocs Material, mdBook, markdownlint-cli2. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 052 - Helper PC capability registry

Goal: Register helper CPUs, RAM, disk, supported languages, and tool versions before routing work.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-052-helper-pc-capability-registry.md` and `docs/prd/slice-052-helper-pc-capability-registry.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/work_routing/*; backend/apps/backpressure/*; tests/test_helper_capabilities.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Helper PC capability registry
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: pgRouting. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 053 - Resource budget enforcement

Goal: Apply RAM, CPU, disk, parallelism, and helper budgets to every heavy library lane.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-053-resource-budget-enforcement.md` and `docs/prd/slice-053-resource-budget-enforcement.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/backpressure/policies.py; tests/test_resource_budget_policy.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Resource budget enforcement
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Boost Graph Library. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 054 - Repair command standard

Goal: Give every derived library-backed state check, rebuild, repair, audit, and contract-check commands.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-054-repair-command-standard.md` and `docs/prd/slice-054-repair-command-standard.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/*/commands/*; tests/test_repair_command_standard.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Repair command standard
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Deepchecks, QuickCheck, Zstandard, cppcheck, quickcheck-rs, staticcheck, govulncheck, pip-audit. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 055 - Migration and old-path deletion

Goal: Delete legacy Python fallbacks, old sidecar branches, disabled features, and duplicate modules after acceptance.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-055-migration-and-old-path-deletion.md` and `docs/prd/slice-055-migration-and-old-path-deletion.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: audit/deleted-old-paths.md; tests/test_old_path_absence.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Migration and old-path deletion
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: trafilatura, CRoaring, m2cgen, SymPy, Zstandard, GoogleTest. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 056 - Library bank review workflow

Goal: Add mandatory review questions, owner signoff, and acceptance records for each accepted library.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-056-library-bank-review-workflow.md` and `docs/prd/slice-056-library-bank-review-workflow.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: backend/apps/library_registry/reviews.py; docs/review-rubric.md; tests/test_library_review.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Library bank review workflow
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Boost Graph Library. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 057 - Operator runbook

Goal: Create noob-friendly commands for checking, repairing, benchmarking, and auditing libraries.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-057-operator-runbook.md` and `docs/prd/slice-057-operator-runbook.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: docs/runbooks/library-expansion-runbook.md; backend/apps/diagnostics/management/commands/*. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Operator runbook
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: libxml2, EWAHBoolArray, SHAP, Lean, zlib-ng, OpenTelemetry. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 058 - Agent prompt pack

Goal: Create reusable prompts for Claude, Codex, Gemini, and Antigravity that preserve boundaries.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-058-agent-prompt-pack.md` and `docs/prd/slice-058-agent-prompt-pack.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: docs/agent-prompts/library-expansion/*; tests/test_prompt_pack_contract.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Agent prompt pack
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Gumbo parser, MinHashLSH Forest, Evidently, LiquidHaskell, Snappy, Prometheus. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 059 - End-to-end acceptance audit

Goal: Prove every accepted library has owner, boundary, tests, benchmarks, health, docs, and no fallback.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-059-end-to-end-acceptance-audit.md` and `docs/prd/slice-059-end-to-end-acceptance-audit.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: audit/library-expansion-acceptance.md; backend/apps/library_registry/audit.py. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: End-to-end acceptance audit
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Boost Graph Library, pip-audit, cargo-audit, npm audit, SLSA provenance. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

### Slice 060 - Final cutover and freeze

Goal: Freeze the registry baseline and require future changes to use the intake process.

Boundaries: Call only the owner API. Do not add private imports, fallback branches, helper-PC truth, or correctness outside Haskell-owned decisions.

ADR and PRD: Create or update `docs/adr/slice-060-final-cutover-and-freeze.md` and `docs/prd/slice-060-final-cutover-and-freeze.md`. The ADR records ownership, rejected alternatives, no-fallback behavior, resources, and repair path. The PRD records user value, non-goals, states, access, and acceptance.

Expected files: docs/specs/fr-approved-library-expansion-bank.md; audit/library-registry-freeze.md. Add owner-module tests, docs, and `audit/` output for decisions.

Requirements: Define DTOs, schemas, typed errors, provenance, health, and repair commands. Register owner, version, license, source URL, package hash, resource class, and status. Add check, rebuild, repair, audit, and contract-check commands for derived state.

Specs and sources: Official library documentation, existing modular-monolith rules, no-fallback rules, source-backed algorithm papers where the slice uses search, graph, optimization, fuzzing, or ranking algorithms.

BDD test cases:

```gherkin
Feature: Final cutover and freeze
  Scenario: Accepted path uses the owner API
    Given the owning module exposes a public API
    When the feature runs through the approved caller
    Then the module records provenance, validates inputs, and returns a typed result
    And no private module import or old-path fallback executes

  Scenario: Required dependency is missing or unhealthy
    Given the required library, service, index, or native artifact is unavailable
    When the feature runs
    Then the module returns blocked, repair-required, or rebuild-required
    And it does not silently skip validation or route to an old implementation
```

Edge cases: Handle empty inputs, duplicates, stale metadata, corrupt artifacts, schema mismatch, missing permission, timeout, partial helper results, interrupted rebuilds, disk pressure, memory pressure, and invalid UTF-8. Record typed rejection reasons.

Reusable libraries to look out for: Kuzu, LightGBM, Deepchecks, Hedgehog, jemalloc, Grafana Beyla. Use only after gates. Prefer accepted libraries.

Resources: Use backpressure RAM caps, explicit CPU budgets, metadata_catalog or approved spill paths, deterministic shards, and helper PCs only for acceleration.

Implementation: Start with a failing test. Implement the smallest real behavior. Reuse owner APIs. Keep functions small. Delete old paths in the same accepted work unit. Run unit tests, static analysis, linting, boundary checks, and benchmarks.

Static analysis and linting: Run the registry tools for the touched language. Use Biome, clang-tidy, cargo clippy, staticcheck, gosec, HLint, pytest, Semgrep, or CodeQL when relevant.

Review: Check ADR, PRD, specs, BDD, edge cases, resources, and ownership. Reject spaghetti code, untyped errors, hidden fallbacks, silent skips, overbroad abstractions, hardcoded hosts, hardcoded model names, and useless verbosity.

## 7. Source anchor pack

Use these anchors before implementing slices. Prefer the official project documentation and primary papers over blog posts. Update the ADR if a source changes or conflicts with local constraints.

- Tantivy docs: https://docs.rs/crate/tantivy/latest
- LanceDB docs: https://docs.lancedb.com/
- Apache DataFusion docs: https://datafusion.apache.org/
- Grafana Beyla docs: https://grafana.com/docs/beyla/latest/
- pgvector project: https://github.com/pgvector/pgvector
- Perfetto tracing SDK: https://perfetto.dev/docs/instrumentation/tracing-sdk
- LLVM GWP-ASan: https://llvm.org/docs/GwpAsan.html
- LightGBM ranker: https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRanker.html
- CatBoost ranker: https://catboost.ai/docs/en/concepts/python-reference_catboostranker
- Tree-sitter: https://tree-sitter.github.io/tree-sitter/
- Oxc: https://oxc.rs/
- Biome: https://biomejs.dev/
- Apache Arrow: https://arrow.apache.org/
- DuckDB: https://duckdb.org/
- Polars: https://pola.rs/
- OpenDAL: https://opendal.apache.org/
- Qdrant: https://qdrant.tech/documentation/
- USearch: https://github.com/unum-cloud/usearch
- DiskANN paper: https://www.microsoft.com/en-us/research/project/project-akupara-approximate-nearest-neighbor-search-for-large-scale-semantic-search/
- Broder MinHash: https://www.cs.princeton.edu/courses/archive/spring04/cos598B/bib/Broder97resemblance.pdf
- Malkov and Yashunin HNSW: https://arxiv.org/abs/1603.09320
- Brin and Page PageRank: https://research.google/pubs/the-anatomy-of-a-large-scale-hypertextual-web-search-engine/
- HITS: https://www.cs.cornell.edu/home/kleinber/auth.pdf
- DeepWalk: https://arxiv.org/abs/1403.6652
- node2vec: https://arxiv.org/abs/1607.00653
- Reciprocal Rank Fusion: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
- Team Draft Interleaving: https://eprints.gla.ac.uk/108076/1/108076.pdf
- AFL++: https://aflplus.plus/
- Kani: https://model-checking.github.io/kani/
- cargo-nextest: https://nexte.st/
- ConnectRPC: https://connectrpc.com/
- River Queue: https://riverqueue.com/
- Asynq: https://github.com/hibiken/asynq
- OpenTelemetry: https://opentelemetry.io/docs/
- Sigstore Cosign: https://docs.sigstore.dev/cosign/
- Syft: https://github.com/anchore/syft
- Trivy: https://trivy.dev/
- OSV-Scanner: https://google.github.io/osv-scanner/

## 8. Final acceptance checklist

1. Every accepted library has an owner module, owner API, allowed caller list, and forbidden caller list.
2. Every accepted compiled artifact appears in native runtime health checks and build scripts.
3. Every accepted library has package pinning, source URL, license status, and vulnerability status.
4. Every hot-path replacement has Python baseline, native benchmark, small-medium-large inputs, and recorded result.
5. Every old Python fallback, old sidecar branch, or old direct database path disappears after cutover.
6. Every derived state has check, rebuild, repair, audit, and contract-check commands, or a documented reason why a command does not apply.
7. Every helper-PC path records deterministic manifests, leases, result hashes, and resource budgets.
8. Every GUI surface shows true states only: ready, empty, blocked, rebuild required, repair required, access denied, pending approval, rollback available, or failed with reason.
9. Every agent prompt tells the agent to inspect existing code, reuse accepted libraries, follow TDD, and stop if the planned work violates language ownership.
10. The final audit proves no duplicate libraries serve the same accepted production role without an ADR explaining the split.

## 9. Anti-pattern bank

### Cosmetic dependency

The code imports a package, but no caller uses it, no test fails when it disappears, and no health check sees it. Reject the slice.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

### Fallback import

The code catches ImportError and routes to a Python equivalent after the native artifact fails. Delete the fallback or keep the new dependency candidate-only.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

### Private module bypass

The code imports another module's models, storage, or internal clients instead of its public api.py. Add a public method or move the behavior to the owner.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

### Benchmark theater

The slice benchmarks toy inputs that do not resemble production. Require small, medium, and large fixtures with fixed seeds and reported memory.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

### Helper truth leak

A helper PC writes final state or decides a winner. Convert it to a shard runner that returns hashed evidence to the primary node.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

### Frontend governance

The browser computes approval, threshold, or rank decisions. Move the decision to Haskell or the owning backend module and leave the browser to display state.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

### Library sprawl

Two libraries solve the same accepted role without a boundary. Keep one winner or write an ADR that splits roles by workload.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

### Silent approximation

The code uses sketches, ANN, or probabilistic outputs without recording error bounds. Add exact fixtures and visible approximation labels.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

### Unbounded parallelism

The code uses all cores or unbounded goroutines. Route work through backpressure and resource budgets.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

### Opaque model artifact

A model file appears without schema, provenance, training data reference, runtime compatibility, and rollback proof. Reject it.

Do: add tests that fail on the anti-pattern, document the boundary, and rerun the affected quality gates. Do not: suppress the finding, add a feature flag to route around it, or leave the old path alive after acceptance.

## 10. Future reuse protocol

When a future agent says `need live vector retrieval`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use search_index.api with pgvector first. Use USearch, hnswlib, LanceDB, Qdrant, or DiskANN only in a bake-off slice that records recall, latency, RAM, disk, and rebuild cost. Keep FAISS only for existing approved callers and delete degraded fallback branches. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need full-text search without jvm`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use Tantivy or Postgres full-text candidates behind search_index.api. Use Quickwit for immutable logs or archives, not live ranking. Use Meilisearch or Typesense only for admin UX comparison. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need high-volume json import`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use simdjson plus simdutf in native ingest. Validate schemas through schema_registry. Keep Python orchestration for command flow and reject invalid records rather than silently repairing them. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need unicode-safe text processing`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use simdutf for validation, ICU4C for locale semantics, ftfy for recorded offline repair, and uchardet only when charset metadata is absent. Never let text normalization differ by language without fixtures. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need duplicate detection`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use BLAKE3 or XXH3 for fast fingerprints, MinHash or SimHash kernels for approximate similarity, and CRoaring for candidate sets. Benchmark Rust and C++ contenders and keep the faster accepted path. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need graph diagnostics`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use Apache AGE for stored graph snapshots, GraphBLAS or NetworKit for heavy offline metrics, NetworkX for small reference fixtures, and Haskell governance for acceptance decisions. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need offline ranking model candidates`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use LightGBM, CatBoost, XGBoost, Optuna, and SHAP behind ranking_training.api. Export only artifacts that pass schema, provenance, runtime compatibility, Haskell governance, and GUI approval. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need constrained optimization`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use CVXPY, OR-Tools, OSQP, HiGHS, Z3, or cvc5 in offline diagnostics. Store infeasible constraints and solver settings as evidence. Never let a solver promote active profiles. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need native c++ speed`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use CMake, Ninja, Google Benchmark, sanitizers, Perfetto, GWP-ASan, clang-tidy, and fuzzing. Register the artifact in compiled artifact health checks and delete Python fallback in the same work unit. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need rust speed`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use cargo-nextest, Criterion.rs, proptest, Miri, Kani, cargo-fuzz, and cargo-mutants. Rust wins only with recorded benchmark proof and ownership fit. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need go worker plumbing`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use go-redis, Redis Streams, Redis sorted sets, River or Asynq only as benchmark candidates, ConnectRPC for APIs, pprof, and OpenTelemetry Go. Do not put ranking or correctness logic in Go. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need browser ui quality`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use TanStack Query, TanStack Table, React Hook Form, Zod or Valibot, XState, Radix UI, shadcn/ui, Playwright, Vitest, React Testing Library, MSW, and axe-core. Browser code displays truth; it does not decide truth. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need supply-chain control`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use Syft, Grype, Trivy, OSV-Scanner, pip-audit, cargo-audit, cargo-deny, Cosign, SLSA, in-toto, and secret scanners. Treat scanner output as review input with severity policy. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.

When a future agent says `need documentation agents can reuse`, it must inspect the registry first, pick the smallest accepted library set that fits the owner module, and write a slice-specific ADR before changing code. Use MkDocs or mdBook, Mermaid, markdownlint, Vale, ADR indexes, owner-module tables, and copy-pasteable slices. Keep docs close to tests and implementation files. The agent must report rejected alternatives and the reason each one lost. The agent must leave an audit row so the next session does not repeat the same search.



## Document metrics

Library entries: 256. Word count target: 36,000 to 42,000. Generated word count before this metrics line: 37177.
