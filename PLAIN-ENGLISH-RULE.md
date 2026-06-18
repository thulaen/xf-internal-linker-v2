# Plain-English Communication Rule

**This rule applies to every AI agent that works in this repository: Claude, Codex, Gemini, Antigravity, and every future agent. It is non-negotiable.**

---

## The Rule in One Sentence

Every word you send to the user must be understandable by someone who has never written a line of code in their life.

---

## PARAMOUNT — Plain-English Communication Rule

- **Commit-scope** — the files in the commit plus direct helper files needed to check those files, such as nearby tests or benchmark files.

Every response, commit message, error report, status update, and user-facing surface MUST be written in plain English the user can understand. The user is a vibe coder — they use AI exclusively and don't write code.

**Every substantive response must contain all three of these parts:**

1. **What I'm doing / will do** — describe the action in everyday words. Define every technical term the moment it first appears. No unexplained acronyms (FR-XXX, ISS-XXX, RPT-XXX, MMR, BGE-M3, FAISS, RSQVA, PPR, HITS, HGTE, etc.).

2. **What was accomplished** — at the end of every change, state in plain English what now works that didn't before, plus which files changed and why.

3. **What has issues or errors** — surface failures honestly. If something broke, say what broke, why, and what you'll do about it. Never bury errors in jargon. Never silently move on. Never claim success when something is partial. If a step was skipped, say so.

Skipping any of the three parts is a protocol violation. Silence on errors is forbidden.

### Decision Point line on every task-complete chat response (added 2026-05-20)

A **Decision Point line** is required at the end of every task-complete chat response:
one short line, written in plain English, that tells the user what you are waiting on
and what their choices are right now. It starts with the literal text `Decision Point:`
so the user can always find it at the bottom of a finished reply.

- A task-complete chat response is any reply where you have finished the work the user
  asked for in this turn (the task is done, blocked, or needs the user to choose).
- The Decision Point line states the single next decision the user faces — for example,
  "Decision Point: the change is ready to commit — say `commit` to land it, or tell me
  what to adjust."
- If there is nothing for the user to decide, say so plainly:
  "Decision Point: nothing needed from you — the task is complete."

This line removes ambiguity about whether a turn is finished and what the user should do
next. It is required only on task-complete responses, not on every intermediate message.

---

## Before You Send — Mandatory Self-Check

**Before sending ANY response, answer YES to all seven questions. If any answer is NO, rewrite the response first.**

1. **Terms defined?** Is every technical term defined in plain English in the same sentence where it first appears?
2. **Grandmother test?** Would someone who has never written code understand every sentence without needing to look anything up?
3. **Three parts covered?** Have I stated what I'm doing, what was accomplished, and what (if anything) has issues?
4. **No bare acronyms?** Have I avoided all unexplained acronyms — FR-XXX, ISS-XXX, MMR, BGE-M3, FAISS, RSQVA, and any other project shorthand?
5. **No analogies?** Have I removed every analogy? Bad: "the test is the canary in the coal mine." Good: "if a test fails, you know there is a bug." (Added 2026-05-12 — applies to every response, every surface.)
6. **No metaphors?** Have I removed every metaphor? Bad: "the rule's floor only goes up." Bad: "the gate blocks the merge." Bad: "the noise drowns out the signal." Good: "the rule's minimum value can be raised but not lowered." Good: "the check stops the merge from completing." Good: "the warning messages make it hard to see the real errors." (Added 2026-05-12.)
7. **Coverage summary in percentages?** For any `[COVERAGE SUMMARY: ...]` marker, are BOTH `target=` and `actual=` expressed as percentages with the `%` symbol? Bad: `target=Level A`. Bad: `actual=8/8 tests passing`. Good: `target=90%`. Good: `actual=92.5%`. (Added 2026-05-12.)

**If ANY answer is NO → rewrite before sending.**

---

## PARAMOUNT — Plain-English Absolutism (added 2026-05-12)

This section strengthens the rule above. It applies to **every response, every commit message, every pull-request description, every AGENT-HANDOFF entry, every REPORT-REGISTRY entry, every chat message, every error message, and every other user-facing surface**.

### Rule 1 — No analogies, no metaphors, no rhetorical devices

Every sentence must say what it means directly. Replace every figure of speech with the literal statement.

**Forbidden patterns:**

- Analogies. Anything that compares the topic to something else for explanation. Example to avoid: "tests are the canary in the coal mine." Replacement: "if a test fails, you know there is a bug somewhere."
- Metaphors. Anything that describes the topic in non-literal terms. Examples to avoid: "the ratchet only goes up," "the gate blocks the merge," "the floor raises," "the noise drowns the signal." Replacements: "the minimum value can only be raised, never lowered," "the check stops the merge," "the minimum required value goes up," "the extra messages make it hard to see real problems."
- Idioms. Anything whose meaning is not literal. Examples to avoid: "in good shape," "papering over," "out of the gate." Replacements: state the literal meaning instead.

**Why this rule exists:** the user is a vibe coder who reads everything an agent writes. Figures of speech force the reader to decode the agent's intent. Direct language does not. Direct language also keeps the writing measurable against readability scores.

### Rule 2 — Readability targets

Every response should hit these scores when measured by a standard readability tool:

- **Flesch Reading Ease: 60 or higher where practical.** Below 60 the text is in the "fairly difficult" band.
- **Flesch-Kincaid Grade Level: 8.9 or lower.** A 9th grader should be able to read it.
- **Passive sentences: 5.2 percent or lower.** Active voice is shorter and clearer.

The agent does not need to run a tool on every response. The targets are the standard the writing must aim at. Common drift to watch for: long sentences with multiple clauses, passive voice ("was caught by"), and dependent-clause stacking.

### Rule 2a - BDD for plans and summaries

BDD means behavior-driven description. When Claude or Codex writes a plan, summary, or handoff that describes behavior, use `Given / When / Then`. The words must describe what the user can expect, not internal code trivia. Code-changing handoff entries must include `[BDD PROOF: Given ... When ... Then ...]`.

### Rule 3 — Coverage summary must use percentages

Every `[COVERAGE SUMMARY: ...]` marker MUST express both `target=` and `actual=` as percentages with the `%` symbol. Examples:

- **Correct:** `[COVERAGE SUMMARY: target=90% actual=92.5% — met]`
- **Correct:** `[COVERAGE SUMMARY: target=75% actual=68.0% — not met — Angular component coverage dropped 3pp on this PR; will add 2 more spec files]`
- **Wrong:** `[COVERAGE SUMMARY: target=Level A actual=8/8 tests pass — met]` (no percentages)
- **Wrong:** `[COVERAGE SUMMARY: target=N/A actual=N/A — met]` (no percentages)

When the task is documentation only and no code coverage applies, write `[COVERAGE SUMMARY: target=0% actual=0% — met (no code changes; no coverage applicable)]` so the marker still parses.

The pre-commit hook `.githooks/check-registry-read.py` enforces the percentage format on any AGENT-HANDOFF entry that touches code.

### Why these rules are PARAMOUNT

The user reads every word. The user does not write code. Every metaphor the user has to decode takes them further from what the agent is doing. Every percentage skipped or replaced with a vague phrase like "Level A" makes the coverage measurement unverifiable.

Skipping any of the three rules above is a protocol violation. The rule cannot be overridden by an in-session prompt. Every AI agent — Claude, Codex, Antigravity, every future agent — applies this rule from session start to session end without exception.

---

## Jargon Glossary — Use These Substitutes

When you must mention a technical concept, use the plain-English version from the left column. Never use the right column without defining it first.

| Plain-English substitute | Technical jargon to avoid (or always define) |
|--------------------------|-----------------------------------------------|
| number-fingerprints that capture meaning | embeddings |
| our similarity search engine that finds alike content | FAISS |
| a database update script | migration |
| a scoring factor | signal |
| FR-011 Early Main-Content Matching â€” the field-aware relevance update that tracks whether matched words came from the title, headings, or first main-content passage | Early Main-Content Matching |
| re-sorting results using better criteria | reranking |
| a setting that controls how the AI behaves | hyperparameter |
| code that runs thousands of times per second | hot path |
| a speed-boosted module written in a faster language (Rust, via PyO3 + maturin) — this is the project's compute path; see RUST-FIRST.md | Rust extension |
| RETIRED 2026-06-06 — kept for history. The project moved off C++ to Rust-only for hot paths (ADR 0007). Old meaning: a speed-boosted module written in C++. Use "Rust extension" instead | C++ extension (RETIRED) |
| the background task runner | celery worker |
| the framework that builds the visual interface | Angular |
| the framework that handles data storage and business logic | Django |
| the read-only screen that shows local accuracy-check reports for MATLAB and number comparisons | Accuracy Lab |
| the math program used as an independent checker for numeric results | MATLAB |
| a background checker that physically blocks saves if coding rules (like writing tests first) are skipped | Agent Guard Daemon |
| the Django setting that lists the app's database connections | DATABASES |
| the Django setting value that selects which database type Django should use | ENGINE |
| a packaging system that makes the app run the same everywhere | Docker |
| profile data that shows where code spends time or memory while the app runs | OpenTelemetry Profiles |
| the local service that stores and searches profile data | Pyroscope |
| a tool that records a timeline of what native (C++/Rust/Go) code is doing so slow spots become visible | Perfetto |
| a memory-safety watchdog that samples native code while it runs and flags use-after-free or buffer-overflow bugs | GWP-ASan |
| grouping near-duplicate issues together so one fix closes the whole family | root-cause clustering |
| the background service that groups near-duplicate issues by their underlying cause | clusterd |
| a fast way to estimate how similar two sets of words are without comparing every element | MinHash |
| a fast way to find likely-similar items without comparing every possible pair | LSH / locality-sensitive hashing |
| an automatic tuner that searches for the best settings by trying many combinations and keeping the best | Optuna |
| the OpenTelemetry data format used to send traces, metrics, logs, and profiles between services | OTLP |
| a collector setting that turns on a not-yet-default capability | feature gate |
| a short written plan with sources that proves why a speed or profiling change is designed that way | performance spec |
| a software design document that states how a code change should be built and checked | SDD / software design document |
| a product requirements document that states what a user-facing change must do | PRD / product requirements document |
| approved lesson labels that let agents find the same trap across different folders | concept tags / controlled vocabulary |
| a commit proof marker that lists the current source-backed specs checked before code was written | SPEC PROOF marker |
| a commit proof marker that names the code area, the spec read, whether the spec covered the change, and which sources filled any missing requirement | SPEC RESEARCH GATE marker / specification and research gate |
| a spec marker that records when a spec was reviewed and when it must be reviewed again | SPEC FRESHNESS marker |
| a commit proof marker that says the agent compared the code to the written spec before commit | SPEC CODE REVIEW marker |
| the cleanup step a shell script runs when it finishes normally | EXIT shell signal |
| the interruption signal sent when a person stops a shell script | INT shell signal |
| the stop signal Docker sends when it asks a shell script or container to shut down | TERM shell signal |
| a Dockerfile line that sets a value the container can read while it runs | ENV |
| a Dockerfile line that sets the folder future commands run from | WORKDIR |
| a Dockerfile line that sets the default command for the container | CMD |
| RETIRED 2026-06-06 — kept for history. streamd was a Go service; the Go tier is removed (ADR 0007). Old meaning: a Go service that received live events and let other parts of the app read them back in order | streamd (RETIRED) |
| a service that stores short messages and hands them to other app parts in order | message broker |
| a short repeat-detection code made from an event's source, type, and payload | dedupe key |
| RETIRED 2026-06-06 — kept for history. C/C++/Go/Haskell/Lua are removed; the only compiled language is Rust, built through the Docker-managed maturin path (see RUST-FIRST.md). Old meaning: the repo rule file for how Docker built and stored compiled-language outputs | COMPILED-LANGUAGE-RULES (RETIRED) |
| a set of common Linux command-line tools used by many scripts | GNU |
| a book reference for an agile testing source | ISBN-978-0321534460 |
| RETIRED 2026-06-06 — kept for history. Go is removed from the backend (ADR 0007). Old meaning: the Go setting controlling how many CPU threads Go could run at once | GOMAXPROCS (RETIRED) |
| a setting or path that is meant to run only on a remote service, not on the local computer | REMOTE-ONLY |
| a short example name for an environment variable in tests and scripts | VAR |
| storing compiled files by their exact file fingerprint so identical outputs use one saved copy instead of piling up | content-addressed compiled artifact store |
| a 64-character file fingerprint used to prove two files have exactly the same bytes | SHA-256 hash |
| the active compiled files the app imports or runs after they have passed a verification check | active compiled artifacts |
| temporary compiler work folders that can be deleted and rebuilt later | compiled scratch folders |
| the container setting that tells Python where to look for importable modules | PYTHONPATH |
| a GitHub Actions job or CMake target group that runs a repeatable project check | WORKFLOW |
| a CMake built-in variable that names the current operating system inside the build script | SYSTEM |
| a CMake list value used to collect source files or target names before a build step | LISTS |
| an expected test item showing an extra matched phrase or result list entry | MORE |
| Linux running inside Windows | WSL |
| how many different paths exist through the code (lower = simpler) | cyclomatic complexity |
| number-fingerprints stored in a searchable index | vector store |
| turning text into number-fingerprints | encoding / vectorising |
| a ranked list of similar content | nearest-neighbour results |
| a caching layer that holds recently used data in memory | Redis |
| the database | PostgreSQL / pgvector |
| the main app file | manage.py |
| the website's navigation menu | sidenav |
| a test that runs without needing the full app running | unit test |
| a test that boots the full app | integration test |
| a behavior plan written as `Given`, `When`, and `Then` so the user sees the expected outcome first | BDD / behavior-driven description |
| writing or updating a small test before or alongside the code, then rerunning it until it passes | TDD / test-driven development |
| Kubernetes permission rules that decide what a pod identity may do | RBAC |
| the identity a pod uses when it talks to Kubernetes | ServiceAccount |
| a Kubernetes permission rule | Role |
| the link between a pod identity and a Kubernetes permission rule | RoleBinding |
| a Kubernetes pod traffic rule | NetworkPolicy |
| a Kubernetes key-value settings object that pods and jobs can read | ConfigMap |
| a ready-made container image that holds the tools for one kind of test job | runner image |
| a temporary database made for one test job shard so tests do not share writes | sharded test database |
| the current Kubernetes pod-network mode used by this cluster | VXLAN |
| a Kubernetes Service that points at something outside the pod set because it has no pod selector | selectorless Service |
| a Kubernetes object that lists the network addresses behind a Service | EndpointSlice |
| a small database connection pooler that reuses real PostgreSQL connections | PgBouncer |
| a Redis-compatible cache server used here for disposable cache and live browser messages | Valkey |
| a Kubernetes service port that opens on each node so a browser can reach a pod | NodePort |
| the Kubernetes control address that `kubectl` contacts before it can list nodes or services | Kubernetes API server |
| a numbered network doorway on a machine; `6443` is the usual Kubernetes API server port in this plan | TCP port |
| the build tool that creates repeatable outputs from a declared build graph | Bazel |
| the small launcher that downloads and runs the pinned Bazel version | Bazelisk |
| the optional Bazel web service for shared build cache and build result viewing | BuildBuddy |
| a paid Google service that runs short batch jobs and stops when they finish | Google Cloud Batch |
| a cheaper Google Cloud virtual machine that can be stopped by Google at any time | Spot VM / Spot VMs |
| a saved Google Cloud cost table that scripts can query before spending more money | billing export |
| a Google Cloud spending alert that can call another service when a budget threshold is reached | budget notification |
| the folder setting that tells the live backend where to write resolved-issue lookup audit logs | XF_AUDIT_DIR |
| the settings file that tells kubectl how to reach a Kubernetes cluster | kubeconfig |
| the command-line tool that talks to Kubernetes | kubectl |
| the user's Windows laptop that controls the cluster but should not run builds after cutover | MSI |
| the lightweight Kubernetes distribution running the two-node cluster | k3s |
| Kent Beck's book identifier for the test-first programming source used by the rule docs | ISBN-978-0321146533 |
| the international test-documentation standard cited by the rule docs | ISO-IEC-IEEE-29119-3-2021 |
| the official web protocol standard cited by the evidence rule docs | RFC-9110 |
| the commit marker that records whether the agent found problems before continuing | DECISION |
| the second word in the decision-point marker name | POINT |
| the commit marker that records the end of a work session | SESSION |
| the second word in the session-close marker name | CLOSE |
| a follow-up marker word meaning the later agent or later step must continue the work | NEXT |
| the standard way modern AI agents call external tools | MCP / Model Context Protocol |
| a small local coordination database where manually started agents record who joined, what they claimed, what needs review, and who should prepare the final commit | inter-model interface / SQLite-backed coordination pool |
| Anthropic's local AI coding agent that runs in your terminal | Claude Code |
| OpenAI's local AI coding agent that runs in your terminal | Codex / Codex CLI |
| Google's local AI coding agent that runs in your terminal | Gemini CLI |
| Google's local AI coding agent that runs in your terminal | Antigravity |
| a Chrome tool server that lets an AI agent open a browser, inspect console errors, check network requests, take screenshots, and run performance checks | Chrome DevTools MCP / chrome-devtools-mcp |
| Anthropic's monthly subscription that includes Claude Code | Max 5x |
| a long string the app uses to prove it's allowed to call its own backend | Django Token |
| running an AI agent without a chat window — give it one prompt, take its answer | headless mode |
| a single number that combines several scoring factors into one final ranking number | composite score |
| the Rust module that scores and orders link candidates, checks weight safety, and explains each decision | RankingDecisionEngine |
| a saved, numbered, never-edited record of exactly which ranking weights were live at a moment in time | RankingPolicy / ranking policy |
| the one service that turns presets, manual edits, and tuner results into the single live set of ranking weights | PolicyResolver / policy resolver |
| scoring the same candidates a second time with proposed new weights, without changing what reviewers see, to test the new weights safely | shadow scoring / shadow pass |
| re-scoring old suggestions with different weights to see how the ranking would have changed | replay / what-if re-scoring |
| a statistical test that watches results as they arrive and stops as soon as there is enough evidence to accept or reject a change | SPRT / sequential probability ratio test |
| RETIRED 2026-06-06 — kept for history. Go is removed from the backend (ADR 0007). Old meaning: a Go mutation-testing tool. Rust uses its own mutation tooling | go-mutesting (RETIRED) |
| a Python test tool that makes small deliberate code changes and checks whether the tests catch them | mutmut / MUTMUT |
| test changes that were not caught by the test suite | mutation survivors / MUTATION SURVIVORS |
| the textbook Mining of Massive Datasets, used as a source for scoring and data-processing ideas | MMDS |
| a tag we put on a link suggestion to mark it as picked but not yet applied | proposed |
| a small support command used by another tool | helper / HELPER |
| a tracked problem or follow-up item in the app's work queue | issue / ISSUE / ISSUES |
| saved in the database or audit log | recorded / RECORDED |
| Windows' built-in tool that runs a script at a specific time and date | Windows Task Scheduler |
| a way an AI agent talks to a tool by exchanging text on standard input/output | stdio |
| the shell setting that tells a script where to split text while reading it | IFS / Internal Field Separator |
| a way for a server to push updates to a browser as soon as they happen | HTTP-SSE / Server-Sent Events |
| a small program that lets you run AI language models on your own laptop | Ollama |
| an older mathematical method for securing data | RSA |
| a smart algorithm that groups similar items together | HDBSCAN |
| a short text string that says when something should run, e.g. "every Monday at 9am" | cron expression / cron string |
| a Python library that knows how to read cron expressions | croniter |
| a missed scheduled run that the app fired late after noticing it had been skipped | recovered run |
| safe to run twice — running it again doesn't cause harm or duplicates | idempotent |
| a small random delay added so many things don't all run at the exact same second | jitter |
| the current best provider that a new provider must beat before it can replace it | champion provider |
| a provider being tested against the current best provider | challenger provider |
| a saved comparison that scores embedding providers on quality and speed | provider score run |
| a score that checks how high the first useful result appears in the top ten results | MRR@10 / mean reciprocal rank at ten |
| the share of expected useful results that appeared in the top ten results | Recall@10 |
| a statistical check that swaps paired wins and losses to see whether a provider's lead is likely real | paired permutation test |
| a number from 0 to 1 that says how likely the measured lead could happen by chance | p-value |
| stopping a provider from being tested automatically after repeated clear losses | provider ban |
| a separate Docker container that runs alongside the main app | service / sidecar service |
| a config file at the project's root that AI agents auto-discover | .mcp.json / project-scope MCP config |
| numbered "feature request" specs in `docs/specs/fr*.md` — each one a contract for a feature | FR-014 / FR-016 / FR-XXX (any 3-digit feature number) |
| FR-250 — a small C++ helper that holds back outbound API calls so we never go faster than each provider's documented limit (Google Search Console, Google Analytics 4, Matomo, XenForo, WordPress) | FR-250 / API rate limiter |
| a way to compress number-fingerprints so the similarity search engine can fit a giant index in memory by storing each vector as a tiny code instead of a full float array | OPQ / Optimised Product Quantization |
| RETIRED 2026-06-06 — kept for history. BGE-M3 was a self-hosted embedding model that turned text into number-fingerprints; it is no longer the project default. The project now gets embeddings from a paid provider instead of running BGE-M3 locally | BGE-M3 (RETIRED) |
| RETIRED 2026-06-06 — kept for history. Beijing Academy of Artificial Intelligence published the BGE-M3 model that the project used to run locally; BGE-M3 is retired, so BAAI is no longer the source of the project's embeddings | BAAI (RETIRED) |
| ACM Special Interest Group on Information Retrieval — the main academic conference where search and ranking research is published; chunking and passage scoring papers cited in the project come from this venue | SIGIR |
| Asymmetric Distance Computation — the OPQ scoring path that compares a query vector against compressed byte-codes instead of full float vectors; 5-10x faster than the float32 path for the same accuracy | ADC |
| an industry-standard score that measures how good a ranked list is | NDCG / Normalised Discounted Cumulative Gain |
| the field of teaching computers to read and understand text | NLP / natural language processing |
| a smart algorithm Optuna uses to pick the next set of settings to try when tuning | TPE / Tree-structured Parzen Estimator |
| the FAISS index type that combines IVF coarse-grouping with OPQ compression | IVF-OPQ |
| a math optimisation algorithm that finds the best settings to fit a curve to data, using only a small amount of memory — the project uses it to tune the ranker's signal weights | L-BFGS / BFGS / Limited-memory Broyden–Fletcher–Goldfarb–Shanno |
| Windows's normal disk filesystem — does not honour Linux exec-bit permissions, so chmod is a silent no-op there | NTFS / New Technology File System |
| a virtual hard-drive file that Windows uses to store Linux or Docker data | VHDX / Virtual Hard Disk v2 |
| old-school keyword-match scoring used by classic search engines — rewards documents containing the query's words, with diminishing returns and a length penalty | BM25 / Best Match 25 / Okapi BM25 |
| a one-line formula that merges two ranked lists into one final ranking by adding `1 / (60 + rank)` for each item in each list — the standard way to combine meaning-search and word-match results | RRF / Reciprocal Rank Fusion |
| Elasticsearch's "find similar documents by term overlap" query — given one document, finds others that share many of the same words | MLT / More Like This |
| XenForo's plugin that swaps the default MySQL keyword search for Elasticsearch — gives BM25 ranking, highlighted snippets, and faceted filters on the forum | XenForo Enhanced Search |
| a fast keyword-search server that classic search engines run on — the XenForo forum runs one for its built-in search; we can talk to it through the same XenForo API key the importer uses | Elasticsearch / ES |
| running two retrievers side by side (one finds by meaning, one finds by exact words) and merging their results — typically beats either retriever on its own | hybrid retrieval / hybrid search |
| the standing rule that every new feature ships turned-on with a sensible starting value unless it needs external data we don't have on a fresh install | default-on rule |
| a feature that legitimately needs data from outside the project (Google Analytics, Search Console, Matomo, autotuner training history) before it can produce useful output — allowed to default off | external-data-gated |
| FR-019 alert that appears on the diagnostics page when a feature is dormant waiting on data, telling the operator how to activate it | OperatorAlert |
| a ranking scoring factor that rewards a destination page when real visitors often move from the host page directly to that destination page in that order | DSTP / Directed Sequential Transition Probability |
| the saved database row for one ordered visitor movement count from one page to the next page | DirectionalTransitionEdge |
| a random browser-made visit ID that our site sends to both Matomo and Google Analytics so the app can tell when both tools saw the same visit; it is not a name, email, or account ID | first-party visit ID / xfil_visit_id |
| Matomo's report that lists each visit with the ordered page actions inside that visit | Matomo Live visit details / Live.getLastVisitsDetails |
| a Rust-built SQL engine that runs reporting-style queries directly against snapshot files instead of the main database, so heavy number-crunching never slows the app down | DataFusion / Apache DataFusion |
| a compact column-based file format for tabular data — the snapshot files DataFusion queries are stored in it | Parquet / Apache Parquet |
| a Rust-built keyword-search library (a rewrite of Java's Lucene) that runs inside our own process — gives BM25 word-match ranking without running a separate search server | Tantivy |
| the standalone autotuner that adjusts meta-algorithm parameters (RRF k, BM25 k1/b, MMR lambda, etc.) on a monthly schedule with the same challenger-escrow safety as the ranking-weight tuner | meta-algorithm autotuner / FR-018b |
| a security hole that lets an attacker run arbitrary code on the server — e.g. by feeding a malicious pickled blob into a `pickle.loads` call | RCE / Remote Code Execution |
| a stable, permanent identifier for an academic paper or other digital document — looks like `10.1145/1571941.1572114`; the prefix `10.` is what marks it as a DOI | DOI / Digital Object Identifier |
| a fast table-of-data library written in Rust — like a spreadsheet you can drive from Python, but it uses every CPU core automatically; the project uses it to add up millions of analytics rows in seconds instead of minutes | Polars |
| a table of data with named columns, like a single sheet in a spreadsheet — Polars and pandas both work in DataFrames | DataFrame |
| sorting rows into buckets by a column (e.g. by suggestion ID) and then adding up the values inside each bucket — the standard way to roll up raw events into per-thing totals | groupby / aggregate |
| a small, fast file format for tabular data — stores columns separately so reading just one column is much quicker than CSV; used by Polars and pyarrow for weekly model snapshots on disk | Parquet |
| a measure of statistical spread that shrugs off outliers — equals the median of the absolute differences from the median; the project uses it to decide which anchor texts are unusually rare or unusually common | MAD / median absolute deviation |
| a single percentage that says whether changed files became easier to maintain, based on duplicate code, long functions, missing tests, unsafe patterns, and similar issues | quality-debt score |
| the required fast verification mode that splits eligible checks across every reachable helper machine by weight (the Dell helper up to 60 percent, Windows 30 percent, the Mint helper 10 percent), runs them at the same time, then gathers one final result; a machine that is switched off is skipped and its share is handed to the machines that answer | turbo quality model |
| the rule that shares the slow mutation-testing work across three machines by weight (the Dell helper up to a 60 percent ceiling, the Windows laptop 30 percent, the Mint helper 10 percent) and runs them in parallel so the wait is shorter; any machine that is powered off is dropped before work starts and its share is spread over the machines still reachable, so a switched-off box never blocks a commit | weighted machine split / fail-open redistribution |
| the faster second helper PC (20 CPU cores) reached over a secure remote-shell connection; it takes up to 60 percent of the slow mutation work when it is switched on, and is simply skipped when it is off | Dell runner |
| a shared compiled file that the app loads when it runs, so one tested copy can be reused instead of copying the same fast code into several places | dynamic library / shared library |
| classic search-engine word-importance score — rare words across the whole corpus get a higher weight than common ones; combined with term frequency it gives the standard TF-IDF ranking number | IDF / inverse document frequency |
| classic topic-modelling algorithm that groups words into latent topics — each document becomes a soft mixture of K topics; the project uses gensim's implementation for a weekly topic-refresh job | LDA / Latent Dirichlet Allocation |
| the cross-platform Unix-family filesystem standard — `os.replace()` is atomic on POSIX systems and on Windows, which is why the Parquet writer uses it to swap a `.tmp` file onto the live snapshot path without ever leaving a half-written file | POSIX |
| Django's automatic test mode — switched on when the project is run via `manage.py test` or pytest; the codebase reads it through `sys.argv` inspection because Django doesn't set a single `settings.TESTING` flag | TESTING / Django test runner |
| the two-character end-of-line sequence `\r\n` (carriage return then newline) — the line terminator the standard CSV format requires; the project's CSV exports emit CRLF so Excel and other tools parse them without complaint | CRLF / carriage return + line feed |
| NVIDIA's GPU compute platform — the toolkit and drivers that let Python (via PyTorch) push embedding work onto a graphics card. A task marked `gpu_required=True` only runs on a machine where CUDA is installed and a graphics card is detected | CUDA |
| Server Message Block — the file-sharing protocol Windows uses for shared folders over the network. Phase 4.9's helper PCs can mount an SMB share so the main PC reads the helper's outputs back without copying files manually | SMB / Server Message Block |
| Phase 4.9's task-resource decorator — a small piece of metadata attached to each Celery background job (CPU yes/no, GPU yes/no, RAM peak, where it writes its results) that the helper-PC router reads to decide whether to run the task on the main PC or hand it off to a secondary "helper" PC. See `docs/HELPER-CONSTRAINT-RUBRIC.md` for value-picking guidance | @HelperConstraint / HelperConstraint / HELPER-CONSTRAINT-RUBRIC |
| a target the system promises to hit — for example "the home page should load in under 2 seconds, 95% of the time"; the observability stack records numbers so we can tell whether reality is matching the promise | SLO / Service Level Objective |
| a kind of web attack where a malicious site tricks the user's browser into making a request to our site using their saved login cookie — Django's built-in protection adds a hidden token to every form so the server can tell a real submit from a forged one | CSRF / Cross-Site Request Forgery |
| Application Performance Monitoring — the umbrella name for tools that watch how fast and reliable an app is in production (response times, error rates, slow database queries); GlitchTip + Pyroscope + the OpenTelemetry collector together fill this role for the project | APM / Application Performance Monitoring |
| a security header the browser remembers — once a site sends it, the browser refuses to load that site over plain (unencrypted) HTTP for the next year; protects against an attacker downgrading the connection | HSTS / HTTP Strict Transport Security |
| open-source software — code anyone can read, modify, and redistribute for free; the project uses GlitchTip OSS, Pyroscope OSS, etc. (vs. the paid hosted versions of the same products) | OSS / open-source software |
| OpenTelemetry's wire format — the standardised protocol the OpenTelemetry SDK uses to ship traces / metrics / logs to a collector; we send OTLP over gRPC port 4317 inside the docker network | OTLP / OpenTelemetry Protocol |
| the modern way Django talks to the web server — supports both regular HTTP requests and long-running websocket connections; the project's `uvicorn` process runs the ASGI app | ASGI / Async Server Gateway Interface |
| the older way Python web apps talked to a web server — synchronous request/response only, no websockets; superseded by ASGI but still common | WSGI / Web Server Gateway Interface |
| a connection string — a single line that tells the Sentry/GlitchTip SDK where to send error events (project ID + auth key + host); kept in `.env` as `GLITCHTIP_DSN` | DSN / Data Source Name |
| observability hostname check — a startup check that confirms optional monitoring service names, such as `glitchtip` or `otel-collector`, exist before the backend starts sending data to them | observability endpoint check |
| an industry framework for running an IT department — defines vocabulary like "incident", "problem", "change request" the way a hospital defines "triage"; the C++ daily picker spec borrows ITIL severity levels | ITIL / IT Infrastructure Library |
| the public ID for a known security flaw — looks like `CVE-2024-12345`; `pip-audit` checks the project's installed packages against this database every night | CVE / Common Vulnerabilities and Exposures |
| the 0–10 score that says how bad a CVE is — 0 trivial, 10 game-over; the auto-issues priority formula multiplies CVSS by recency and blast-radius | CVSS / Common Vulnerability Scoring System |
| GitHub's own security-advisory database — an alternative ID for vulnerabilities (`GHSA-xxxx-xxxx-xxxx`); pip-audit reports both CVE and GHSA when both are assigned | GHSA / GitHub Security Advisory |
| a Web Vital metric that measures how long the page takes to react after the user clicks/taps — replaced FID in 2024 as the standard responsiveness yardstick | INP / Interaction-to-Next-Paint |
| the legacy responsiveness Web Vital — measured the delay between a click and the browser starting to handle it; replaced by INP | FID / First Input Delay |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007); native extensions are built in Rust through the Docker-managed maturin path. Old meaning: Microsoft's Visual C++ compiler used to build C++ extensions on Windows | MSVC / Microsoft Visual C++ (RETIRED) |
| the four scoring components in the daily issue picker — Severity (how bad), Recency (how new), Regression (was-fine-yesterday), and Akaike Information Criterion (penalty for touching many modules); blended into one priority score per issue. (Note: the picker was originally written in C++; C++ is removed, so any port lives in Rust per ADR 0007) | SEV / REC / REG / AIC |
| the international rulebook for making websites usable by people with disabilities — covers things like keyboard navigation, screen-reader support, color contrast; "AA" is the middle compliance level most enterprises target | WCAG / Web Content Accessibility Guidelines |
| the JavaScript view of CSS — every loaded stylesheet exposes a `cssRules` array the browser keeps in sync; we walk it to debug why a CSS rule isn't winning the cascade | CSSOM / CSS Object Model |
| the standard file format for translation work — an XML file with one entry per source string and a `<target>` slot the translator fills in; produced by `ng extract-i18n` and consumed by `ng build --localize` | XLF / XLIFF / XML Localization Interchange File Format |
| the old session-start rule that required three AutoIssue fixes before new work; this wording is historical only and is forbidden in new handoff entries because the current rule requires 30 real AutoIssue fixes | auto-fix-3 / auto-fix-3 satisfier / fix three before any new task |
| a database row that records one bug, test failure, missing check, or code-quality problem for agents to fix later | AutoIssue / AUTOISSUE |
| a reusable database category for AutoIssues, such as security, performance, correctness, or observability; agents should use these rows instead of inventing one-off issue shapes | AutoIssueCategory |
| the command agents run after their scoped code review when they find a bad practice; it records the finding in the AutoIssue table and can mark it fixed with a lesson when the same task already repaired it | log_self_review_issue |
| the required marker before code starts; it states the coverage target, test commands, mutation and benchmark needs, reuse check, shared-library choice, and 10x / 100x scaling result | STANDARDS READY marker |
| the required marker before the final summary; it states what code was reviewed, which AutoIssues were logged, which fixes were applied, and whether tests and coverage passed | SELF REVIEW RESULT marker |
| the required marker proving Claude or Codex explained the work as a user-facing behavior scenario using `Given`, `When`, and `Then` | BDD PROOF marker |
| the required marker proving Claude or Codex wrote or updated a focused test before or alongside code and reran it until it passed | TDD PROOF marker |
| the session-start marker proving the agent read the always-on "sticky note" policy (Sticky #1, the spec-driven gradual rewrite rule) before writing code; the all-caps form `STICKY` is the marker name, not a new concept | STICKY 1 READ marker / STICKY |
| a compact database record that stores the useful result of a test, coverage, mutation, security, or quality check without keeping huge report folders | QualityEvidence |
| a deduped compressed piece of a raw quality report that is kept for weekly agent memory without saving the full report folder | QualityRawSnippet |
| one saved weekly sample of raw quality-report text, kept only once per week and deduped by content | weekly raw snippet |
| a coverage rule for existing files: the required minimum for that file may stay the same or increase, but it must not decrease; new files still have to meet the full target immediately | ratchet policy / coverage ratchet |
| a recorded full-repo quality gap that agents must pay down later; it is tracked with evidence and AutoIssues, but it does not block an unrelated normal commit while the repo is still below the target | quality debt |
| a JSON file that lists Docker volumes and host folders self-pruning must never delete | protected-data map |
| the minimum disk space that must stay free for app data, embeddings, backups, and database growth | protected reserve |
| the free-space number where the app starts safe cleanup before storage becomes dangerous | cleanup watermark |
| the rule that keeps disposable tool caches for 3 days normally, tightens to 2 days under disk pressure, and never deletes app data or embeddings | tool cache policy |
| shared Docker volumes used by many tool containers so package downloads are stored once instead of copied into each container | deduped tool-cache volumes |
| the required number of issues an agent must fix before its handoff can be accepted | quota / QUOTA |
| the marker line every AI agent puts in its first response proving it read the open auto-issues + Report Registry — looks like `[REGISTRY READ: 5 open auto-issues, 12 open registry findings — picked: #ISS-101, #ISS-102, #ISS-103]`; required by the ABSOLUTE rule in CLAUDE.md / AGENTS.md / CODEX.md / GEMINI.md | REGISTRY READ marker |
| the backend command that checks the AutoIssue database before a handoff commit is accepted; it proves the 30 picked issue IDs are resolved, have a resolve time, have lessons written down, and were resolved after the previous handoff | verify_autoissue_quota |
| the second-line marker an AI agent posts after running `search_resolved_issues` for a touched code area — looks like `[RESOLVED HISTORY: 3 prior fix(es) read in backend/apps/audit]`; proves the agent read prior `lessons_learned` so it doesn't repeat known traps | RESOLVED HISTORY marker |
| a `Path: <repo-relative-path>` argument the agent passes to `manage.py search_resolved_issues` — surfaces the trap + fix-shape from every prior fix in that directory so the next session doesn't repeat the mistake | search_resolved_issues |
| the registry of every per-content database table that follows the `(content_hash, signal_version) skip-if-unchanged + supersede + retention` pattern — defined in NO-DUPLICATES.md, audited at boot via `apps.core.services.self_test_smoke.run_startup_smoke_tests`, gated in CI by `scripts/verify_dedup_invariant.py` | NO-DUPLICATES invariant / no-dups invariant |
| the canonical Python registry that lists every weight + meta-algorithm parameter the autotuner is allowed to adjust — at `backend/apps/suggestions/tunable_registry.py`; new keys MUST land here in the same commit they're introduced (per `docs/AUTOTUNER-FUTURE-AWARENESS.md`) | tunable_registry / BLEND_WEIGHTS / META_PARAMS |
| the file every AI agent must read before any task — consolidates the "fix as you go" + "report severe to BOTH AutoIssue + Registry" rules + the auto-fix-3 count in one place; replaces what used to be inline blocks scattered across CLAUDE.md / AGENTS.md / CODEX.md / GEMINI.md | ONGOING-CODE-QUALITY.md |
| a small Python module at `backend/apps/pipeline/services/disk_pressure.py` that pre-flights large file writes against free-disk watermarks (GREEN/YELLOW/RED/CRITICAL) and raises `DiskPressureError` when the projected write would push free disk below the safety margin; refreshed every 60 s by a Celery beat task | disk_pressure / DiskPressureError / require_free_disk |
| Video memory — the dedicated RAM that lives on the graphics card; used to hold model weights and embedding tensors during GPU computation; separate from main system RAM | VRAM |
| NVIDIA's line of graphics cards that support fast AI computation (e.g., RTX 3050, RTX 4090) | RTX |
| Industry-standard tracing/metrics framework used to record what every backend request and Celery task does, where time is spent, and whether errors happened; the project sends OpenTelemetry data to GlitchTip's Performance tab | OpenTelemetry / OTEL |
| OpenTelemetry's profile data — repeated samples of where code spends CPU time, memory, and waiting time; this is separate from traces and metrics and must be checked before source changes | OpenTelemetry Profiles |
| handoff marker proving the agent inspected Pyroscope and OpenTelemetry Profiles before coding; it names the service, touched scope, hotspot count, baseline command, and decision | profiling proof |
| 95th-percentile latency — the response time that 95 out of 100 requests are at or below; the slowest 5 requests out of 100 are worse than this number | p95 latency |
| 99th-percentile latency — the response time that 99 out of 100 requests are at or below; the slowest 1 request out of 100 is worse than this number | p99 latency |
| moving one proven slow component to Rust after measured proof shows normal Python fixes cannot hit the target; Rust is the only native target now (C++ and Go are removed — ADR 0007) | native rewrite |
| a language built for high-speed low-level work where the program has more direct control over CPU work, memory use, and concurrency; in this project that language is Rust (C++ and Go are removed — ADR 0007) | systems language |
| the one implementation that the repo treats as the main source of truth; old versions either call it, are clearly deprecated, or are removed | canonical implementation |
| Remote Procedure Call — one service calls a function that runs in another process or service; used when code crosses a process boundary instead of calling a local function | RPC |
| Foreign Function Interface — the boundary where Python calls into native code or vice-versa; in this project Python calls into Rust kernels (via PyO3) so the slow Python ranking math is replaced by fast Rust kernels. (Was C++/pybind11 before the Rust migration — see RUST-FIRST.md) | FFI |
| Near-Real-Time — describes scoring or retrieval that happens within seconds of an event (vs. batch jobs that run nightly); the project's NRT signals power live confidence-meter updates and the autotuner's short-window feedback loop | NRT || pre-commit hook script at `.githooks/check-file-size.py` that blocks commits adding a file over 1,500 lines (the cap from CLAUDE.md), and prevents grandfathered files (listed in `.githooks/file-size-grandfather.txt`) from growing past their recorded baseline | check-file-size / file-size-grandfather |
| pre-commit hook script at `.githooks/check-no-downgraded-gates.py` that blocks any commit which silently flips a CI gate from blocking to warning-only (`\|\| true`, `continue-on-error: true`, `exit-code: '0'`, `::warning::`) unless the same diff also adds a `# GATE-DOWNGRADE-JUSTIFICATION:` comment with a real reason | check-no-downgraded-gates / GATE-DOWNGRADE-JUSTIFICATION |
| pre-commit hook script at `.githooks/check-frontend-routes.py` that scans every `HttpClient.get/post/put/patch/delete('/api/...')` call in staged frontend TypeScript files and verifies the URL resolves to a real `path('...')` declaration in `backend/apps/**/urls.py`; prevents stale frontend → backend URL drift | check-frontend-routes |
| pre-commit hook script at `.githooks/check-missing-tests.py` that blocks commits which add a new `*.component.ts`, `*.service.ts`, or `backend/apps/*/services/*.py` file without a matching test file (sibling `.spec.ts` for frontend, `test_<base>.py` in same/parent/tests dir for backend) | check-missing-tests |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007); Rust gives memory safety at compile time. Old meaning: a Clang/GCC instrumentation that caught C++ memory-corruption bugs at runtime | ASAN / AddressSanitizer (RETIRED) |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: a Clang/GCC instrumentation that caught data races in C++ at runtime | TSAN / ThreadSanitizer (RETIRED) |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: Intel Threading Building Blocks, the C++ parallel-task scheduler. Rust uses `rayon` for parallel work | TBB (RETIRED) |
| log database — stores every container's stdout line, queryable like a search engine; runs default-on alongside GlitchTip and Pyroscope; reachable at `localhost:3100`; 30-day retention | Loki |
| log shipper — a small agent that watches every running container's stdout and forwards each new line to Loki; runs default-on as the `alloy` service; replaces Promtail (which Grafana retired in March 2026) | Grafana Alloy / Alloy |
| log query language — the search syntax for Loki; example: `rate({container_name="xf_linker_backend"} \|~ "(?i)error" [5m])` says "errors per second in the backend container over the last 5 minutes" | LogQL |
| Alloy's configuration language — looks like HCL/Terraform; defines pipelines as nested blocks (`discovery.docker "containers" { ... }` then `loki.source.docker "all" { ... }`); the project's pipeline lives in `config.alloy` at the repo root | River |
| retired log shipper — Grafana's original Loki agent; entered maintenance-only mode 2026-03-02; this project never adopted it, jumping straight to Alloy | Promtail |
| OpenTelemetry collector container — the OTel pipeline hub the project still uses for traces and metrics (Alloy lacks the Sentry-format exporter that GlitchTip needs, so otel-collector stays); reads OTLP from the backend + Celery, fans out to GlitchTip + Prometheus + stdout | otel-collector |
| OpenTelemetry Protocol — the wire format every modern tracing/metrics tool speaks; the backend pushes OTLP over HTTP at port 4318 to otel-collector | OTLP |
| auto-issues table — the Django table at `apps.auto_issues.AutoIssue` where every automated finding lands so agents can read them at session start via `manage.py print_open_issues`; current sources are `agent`, `glitchtip`, `pyroscope`, `tempo`, `loki`, `faro`, `mutation`, `fuzz`, `contract`, and `gh_ci` | AutoIssue |
| same-day CPU bottleneck check — Pyroscope picker that ranks functions by self-time over the last hour and files an AutoIssue for any function above a percentage threshold; works from day one (no week-of-history required) | hotspot detector / pyroscope hotspot |
| repeated-warning detector — Loki picker that groups WARN/ERROR lines by normalized fingerprint (timestamps, PIDs, hex addresses stripped) and files an AutoIssue when one pattern occurs many times in 24 h | hot pattern detector / loki hot pattern |
| short-window WARN/ERROR rate spike — Loki picker that compares the last hour's WARN/ERROR count to the 24-hour average and files an AutoIssue when the multiple is high | warn burst / loki warn_burst |
| placeholder AutoIssue filed when an automated source produced fewer findings than the session-start ritual expects (e.g. Loki has only 2 hot patterns instead of 4); the next agent investigates why the source was empty | picker_drought |
| structured-analysis output format — the standard JSON file every code-quality or security scanner writes; the project uses it for Super-Linter and CodeQL reports | SARIF |
| GitHub's code security scanner that finds likely security bugs and writes one report per supported programming language | CodeQL |
| fast lossless compression that stores the full CodeQL evidence in fewer database bytes while allowing exact restore later | LZ4 |
| a lossless compression method (Zstandard, RFC 8878) that squeezes files smaller than the older "snappy" method at similar speed; the analytics snapshot files are written with it so they take less disk | zstd / Zstandard |
| a fast way to pull lots of rows out of the database in one columnar batch (Arrow Database Connectivity) instead of one Python object per cell; used for the analytics snapshot exports | ADBC / Arrow Database Connectivity |
| a Django test base class that actually saves (commits) its test rows to the database, so code opening a second database connection can see them; the normal test class hides its rows inside an uncommitted transaction | TransactionTestCase |
| Google's regular-expression engine (google-re2) that always finishes in time proportional to the input length, so a malicious string can't make it hang; used for the patterns that read untrusted crawled pages and forum posts | RE2 / google-re2 |
| an attack where a crafted string makes a normal regular expression take exponential time and freeze the program (Regular expression Denial of Service); RE2 prevents it | ReDoS |
| a forecasting tool (from Meta) that learns a page's normal weekly rhythm from its history and predicts a sensible range for the next day; the traffic-spike alert fires only when real clicks jump above that predicted range, so it stops false alarms on ordinary busy days | Prophet |
| the smart **build** helper's rule that sends about 65 percent of ordinary compile jobs to Mint and 35 percent to Windows, chosen by a stable hash so the same target always goes to the same side (this is the Docker-build split — not the mutation-test split, which is the weighted machine split above) | 65/35 build split |
| an AutoIssue created when a compiler or Docker build fails; the short issue row points to full LZ4-compressed terminal output stored separately | build-failure AutoIssue |
| Grafana's frontend telemetry SDK — runs in the browser and ships JS errors, Web Vitals, and session events to the Alloy `faro.receiver` block; the `faro_picker` reads those streams from Loki and files an AutoIssue when a JS error or Web Vital breach repeats; added 2026-05-11 | Faro / Grafana Faro / @grafana/faro-web-sdk |
| Grafana's distributed-trace backend — stores spans organised by traceID so a single trace tree (browser → backend → DB → C++) is queryable end-to-end; runs default-on at `localhost:3200`; otel-collector fans traces out to BOTH GlitchTip AND Tempo so the same trace lives in two stores; added 2026-05-11 | Tempo / Grafana Tempo |
| visualisation UI for Tempo, Loki, Pyroscope, and Prometheus — runs default-on at `localhost:3000`; data sources are pre-provisioned from `grafana/provisioning/datasources/datasources.yaml`; admin password lives in `.env`; added 2026-05-11 | Grafana / Grafana OSS |
| Real User Monitoring — telemetry from real users' browsers (page-load times, JS errors, button clicks) as opposed to synthetic probes; Faro is the project's RUM SDK | RUM / Real User Monitoring |
| Google's three browser-performance metrics — Largest Contentful Paint (page-load speed), Interaction to Next Paint (responsiveness), Cumulative Layout Shift (visual stability); the faro picker files an AutoIssue when one breaches threshold on enough sessions | Web Vitals |
| Largest Contentful Paint — how long until the biggest visible element finishes painting; Google's threshold for "needs improvement" is 2500 ms, which is the project's default Faro alert threshold | LCP / Largest Contentful Paint |
| Interaction to Next Paint — latency between a user click/tap and the next visible frame; replaced FID in 2024; Google's "needs improvement" threshold is 200 ms | INP / Interaction to Next Paint |
| Cumulative Layout Shift — unitless score for how much visible content jumps around while a page loads; lower is better; Google's "needs improvement" threshold is 0.10 | CLS / Cumulative Layout Shift |
| one unit of work in a trace — one HTTP request, one DB query, one function call; spans nest inside each other to form a tree | span |
| a tree of spans tied together by one ID — represents one end-to-end operation across services (browser, backend, DB, worker) | trace |
| the 16-byte hex ID that joins every span in one trace — a GlitchTip error event and a Tempo trace with the same traceID describe the same user request | traceID |
| one pipeline writing the same data to two destinations at once — in this project, the otel-collector traces pipeline now fans each span out to BOTH GlitchTip (Sentry exporter) AND Tempo (otlp/tempo exporter) so the trace lives in two stores | fan-out exporter |
| the project's session-start rule requiring 30 real AutoIssue fixes before any other task - every AI agent must fix three open issues from EACH of the ten sources (agent, glitchtip, pyroscope, tempo, loki, faro, mutation, fuzz, contract, gh_ci); no slice, Mission A task, bug fix, multi-bug task, docs task, or satisfier phrase can replace those fixes | auto-fix-30 / fix thirty before any new task |
| a test that passes only because of the order other tests ran in — it secretly relies on data left behind by an earlier test (a shared global, a leaked DB row, a mutated module-level state); the project now runs every suite in randomised order so these tests fail immediately instead of going green in the wrong situation | order-dependent test / test state leakage |
| pytest plugin that runs tests in a random order — installed in `backend/requirements-dev.txt`; auto-activates the moment pytest starts and prints the seed so a failing order can be reproduced with `pytest --randomly-seed=<seed>` | pytest-randomly |
| Django's built-in test-runner option that shuffles test execution order — `manage.py test --shuffle`; the CI backend-test step uses this so the Django runner gets randomisation even where the pytest plugin doesn't apply | Django --shuffle / manage.py test --shuffle |
| GoogleTest command-line flag (`--gtest_shuffle`) that randomises within-binary test order; paired with `GTEST_RANDOM_SEED=0` to pick a fresh seed each run; set as an environment variable in `backend/extensions/CMakeLists.txt` via `gtest_discover_tests(... PROPERTIES ENVIRONMENT "GTEST_SHUFFLE=1")` so every C++ test binary shuffles automatically | --gtest_shuffle / GTEST_SHUFFLE |
| CTest flag (`ctest --schedule-random`) that randomises the order CTest invokes its registered test executables across runs; complements GTEST_SHUFFLE which handles within-binary order | --schedule-random / ctest --schedule-random |
| the project's two hardware-aware concurrency caps (defined in Phase 2 — `backend/apps/pipeline/services/hardware_profile.py`): `MAX_JOBS_FAST` for fast unit tests (tier-aware 2–8) and `MAX_JOBS_HEAVY` for slow tools like mutation/fuzz/sanitizers (capped at 2 or 3 regardless of tier) so heavy tools cannot oversubscribe the machine | MAX_JOBS_FAST / MAX_JOBS_HEAVY |
| testing the tests — a tool deliberately edits ("mutates") the code (e.g. swaps `==` for `!=`, drops a function call) then runs the test suite; if the tests still pass, the test suite is too weak to catch that regression, the mutant "survived", and CI fails. The discipline is the partner to randomised order: randomisation catches order-dependent tests; mutation catches tests-that-don't-actually-assert. | mutation testing / surviving mutant / mutant survived |
| the Python mutation-testing tool used by this project across backend app code. Invoked via `mutmut run --paths-to-mutate=<path> --runner=<test cmd>`; `mutmut results` exits non-zero if any mutant survived | mutmut |
| the TypeScript / Angular mutation-testing tool used by this project across Angular components and services. Reads `frontend/stryker.config.json`; integrates with Karma so the existing test runner mutates each file in turn | Stryker / Stryker Mutator |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: a C++ bug/memory-risk checker. Rust uses `clippy` instead | cppcheck (RETIRED) |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: a C++ static checker. Rust uses `clippy` instead | clang-tidy (RETIRED) |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: a C++ header-include checker | Include-What-You-Use / IWYU (RETIRED) |
| RETIRED 2026-06-06 — kept for history. Go is removed from the backend (ADR 0007). Old meaning: an all-in-one Go bug/style/safety checker | golangci-lint (RETIRED) |
| RETIRED 2026-06-06 — kept for history. Go is removed from the backend (ADR 0007). Old meaning: a Go security checker | gosec (RETIRED) |
| RETIRED 2026-06-06 — kept for history. C/C++ are removed from the backend (ADR 0007). Old meaning: Meta's static analyzer for C, C++, Java, and Objective-C | Infer (RETIRED) |
| a Python checker that finds risky code patterns such as hard-coded secrets and unsafe function calls | Bandit |
| a Python checker that reports code errors and risky patterns; this project runs the errors-only mode in Docker | PyLint |
| a Python dependency checker that reports installed packages with known security problems | Safety |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: the C++ mutation-testing tool run through Clang. Rust uses its own mutation tooling | Mull (RETIRED) |
| one specific edit rule a mutation tool can apply (e.g. `cxx_relational_replacement` swaps `<` and `>`; `arithmetic_replacement` swaps `+` and `-`). The mutation tool walks the source once per mutator and tries each rule at every applicable location | mutator (mutation-testing sense) |
| LLVM is an open-source compiler infrastructure project that the Clang C/C++ compiler is built on; tools like Mull, libFuzzer, ASan/TSan/MSan, and clang-tidy all ship as LLVM components. When the docs say "Mull works at the LLVM IR level," they mean it edits the intermediate code Clang produces before machine-code emission | LLVM |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: a coverage-guided C++ fuzz tool from LLVM/Clang. Rust fuzzing uses `cargo fuzz` | libFuzzer (RETIRED) |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007); Rust gives memory safety at compile time. Old meaning: a Clang sanitizer that caught reads of uninitialised C++ memory | MSan / MemorySanitizer (RETIRED) |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: a libFuzzer harness file for one C++ function under test | fuzz target (RETIRED) |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: the seed-input directory libFuzzer mutated when fuzzing a C++ target | fuzz corpus / seed corpus (RETIRED) |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: Clang's per-sanitizer ignore-list config | sanitizer blacklist / -fsanitize-blacklist (RETIRED) |
| contract-testing framework — the Angular frontend declares "I will call POST /api/foo with {a,b} and expect {c,d} back"; that contract is saved as a JSON file; the Django backend then has a test that replays each declared interaction and fails the build if the response shape drifts. Catches frontend/backend desync at PR time | Pact / contract testing |
| the central registry server that holds every Pact JSON file (one consumer + one provider + their negotiated contract version). Lives in `docker-compose.yml` under the dev profile when used; the in-repo workflow can also just commit the JSON files directly and skip the broker for simpler one-team cases | Pact broker |
| the discipline of letting the consumer (Angular) define the contract, then making the provider (Django) prove it conforms. The opposite is "provider-driven" where the backend ships an OpenAPI / Swagger spec and consumers adapt — Pact prefers consumer-driven because it makes the consumer's actual usage the source of truth, not a hand-edited spec that can drift | consumer-driven contracts |
| meta-linter — Super-Linter is a single GitHub Action that bundles ~50 different linters (Hadolint, golangci-lint, markdown-lint, yaml-lint, gitleaks, etc.). The project uses it for the linters we don't already run as dedicated jobs (Ruff and ESLint stay separate to avoid duplicate version-pinning) | Super-Linter |
| Hadolint — Dockerfile linter (catches use of `ADD` instead of `COPY`, unpinned base images, `apt-get install` without `--no-install-recommends`, etc.). Runs inside Super-Linter on every PR via `VALIDATE_DOCKERFILE_HADOLINT=true` | Hadolint |
| Gitleaks — secret-scanner that flags API keys, AWS access tokens, private keys, etc. accidentally committed to git history. Runs inside Super-Linter on every PR via `VALIDATE_GITLEAKS=true` | Gitleaks |
| the third required ritual marker line (Phase 7) — proves the agent ran `gh run list --status failure --limit 10` at session start and reviewed the 10 latest failed GitHub Actions workflow runs. Two valid forms: `[CI FAILED RUNS READ: <N> latest — picked: #<id>, ...]` (populated) or `[CI FAILED RUNS READ: skipped — gh unavailable]` (when the gh CLI isn't installed). `.githooks/check-registry-read.py` enforces presence. | CI FAILED RUNS READ marker |
| the PARAMOUNT rule added 2026-05-12 — after writing any code, every agent must run the relevant random-order test suite, read failure output, fix the cause, and re-run until the exit code is zero. Applies to pytest / ng test / ctest invocations equally; the pre-push hook running mutmut / Stryker / libFuzzer / clang-tidy on changed files only counts under the same rule. Silently moving on is a protocol violation | auto-iterate after writing code |
| the project's comprehensive coding rules file at `AI-CODING-GUIDELINES.md` (repo root). Every agent reads it at session start, before every task; it defines the prime directive, source-of-truth order, no-hallucination rules, work loop, code-smell + long-function + bug-fix + test-requirement + property-based + evidence-based + business-logic + state-transition + idempotency + database + error + logging + security + external-service + performance + paid-API + naming + dependency + formatting + type-safety + UI + accessibility + concurrency + refactoring + generated-code + file-editing + test-running rules + Definition of Done + the per-task coverage target table | AI-CODING-GUIDELINES.md / coding guidelines |
| the strict coverage rules file at `docs/CODE-COVERAGE-RULES.md`. Defines Level A/B/C/D, the 14 Level A areas (import normalization / text cleaning / sentence splitting / embedding lifecycle / index build/search / scoring / meta-algo / business logic / near-dup removal / existing-link detection / broken-link detection / approval transitions / permissions / analytics import + Celery idempotency + DB integrity), per-language targets (backend mutation 100%, Angular 95% line + 85% branch + 95% mutation, C++ 100% branch + 100% mutation), property-test invariant menus, drought clause | docs/CODE-COVERAGE-RULES.md / coverage rules |
| the strictest coverage tier in `docs/CODE-COVERAGE-RULES.md` — Modified Condition/Decision Coverage (MC/DC), 100% line + branch coverage, property-based tests, mutation testing, golden-fixture regression tests, end-to-end review-workflow tests, traceability of each test to a rule / FR / invariant. Applied to anything touching business logic, scoring, parsing, security, or financial decisions | Level A / MC/DC coverage |
| Modified Condition/Decision Coverage — DO-178C / NASA NPR 7150.2D structural coverage tier where every Boolean condition in every decision is independently exercised showing it can affect the outcome. The strongest commonly-used coverage criterion; required for Class A / safety-critical software | MC/DC / Modified Condition Decision Coverage |
| an AutoIssue row that flags a missing or insufficient test for a specific Level A area or per-language target. Title begins with `[coverage-gap]`. Source = `agent`. Drained at 10 per session via the standard opening ritual; backlog seeded by FR-251 | coverage-gap AutoIssue |
| the fourth required ritual marker (FR-251) — proves the agent read both `AI-CODING-GUIDELINES.md` and `docs/CODE-COVERAGE-RULES.md` at session start. Exact form: `[GUIDELINES READ: AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]`. `.githooks/check-registry-read.py` enforces presence | GUIDELINES READ marker |
| the fifth required ritual marker (FR-251) — proves the agent picked 10 coverage-gap AutoIssues to drain this session alongside the standard 30 auto-issue picks and 10 latest failed CI runs. Two valid forms: `[COVERAGE GAPS READ: 10 picked — #..., ...]` (populated) or `[COVERAGE GAPS READ: <K> picked + <10-K> to file — #..., (drought; ...)]` (drought) | COVERAGE GAPS READ marker |
| the end-of-slice / end-of-task / end-of-session honesty marker (FR-251) — `[COVERAGE SUMMARY: target=<X>% actual=<Y>% — met / not met — <reason if not met>]`. Honesty is mandatory; claiming "met" when the suite is red is a protocol violation | COVERAGE SUMMARY marker |
| FR-251 — the FR spec governing the strict code-coverage program shipped 2026-05-12. Sets the rules in `AI-CODING-GUIDELINES.md` + `docs/CODE-COVERAGE-RULES.md`; the actual work to achieve the targets lives in ~23 coverage-gap AutoIssues drained 10-per-session. See `docs/specs/fr251-code-coverage-program.md` | FR-251 / code-coverage program |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007); the C++ libFuzzer fuzz targets no longer apply. Old meaning: a fuzz-coverage-gap AutoIssue, one per public C++ module without a matching `fuzz_<name>.cpp` target. Rust fuzzing (`cargo fuzz`) replaces this | fuzz-coverage-gap (RETIRED) |
| an object-oriented design principle that says "only talk to your immediate friends" — a method should only call methods on (a) itself, (b) its parameters, (c) objects it creates locally, (d) its direct component objects. Forbids deep chains like `a.b().c().d()`. Encourages "tell don't ask" redesigns where the caller's friend exposes a method that returns the needed value directly. See `AI-CODING-GUIDELINES.md` § Design principles | Law of Demeter / LoD |
| a design principle that each module owns exactly one responsibility. Test: can you describe the module's job without using the word "and"? Mixing import-parsing + scoring + persistence in one function violates SoC; split into three functions. See `AI-CODING-GUIDELINES.md` § Design principles | Separation of Concerns / SoC |
| a design principle that says validate inputs at the boundary and raise immediately on invariant violations. Don't paper over with silent defaults that hide the bug. A `ValueError("weight must be ≥ 0")` at function entry is far easier to debug than a wrong answer five layers deep. See `AI-CODING-GUIDELINES.md` § Design principles | Fail Fast |
| "Keep It Stupidly Simple" — pick the simplest design that solves the real problem. Three similar lines is better than a premature abstraction. Don't design for hypothetical future requirements. Pairs with DRY; they argue with each other on purpose | KISS |
| "Don't Repeat Yourself" — when the same logic appears 3+ times AND is genuinely re-usable, extract a named helper. Two occurrences usually aren't enough; the third occurrence proves the pattern. Pairs with KISS | DRY |
| the failure mode where you abstract code that doesn't justify abstraction — an abstraction with one caller, where the duplicated code is shorter than the abstraction's signature, or where the justification is "I might need this elsewhere later". The cure is to leave the duplication and revisit when a real third caller appears. See `AI-CODING-GUIDELINES.md` § KISS and DRY | over-DRY trap |
| a commit that does one thing, with a title under 70 chars, a body explaining the WHY (not the WHAT), and a reference to any tracked issue ID. Forbidden generic titles: `fix`, `update`, `wip`, `stuff`, `misc`. See `AI-CODING-GUIDELINES.md` § Commit-message rules | atomic and descriptive commit |
| the explicit human-approval gate required before any code is written for a change that touches core architecture, database schema (data migration), global state, public API contract, security model, or ABSOLUTE-rule-adjacent territory. Format: `[REVIEW GATE: awaiting approval]` after a 3-5 bullet summary. Cannot be bypassed by auto mode or session prompt. See `AI-CODING-GUIDELINES.md` § Major-change review gates | review gate / REVIEW GATE marker |
| a stable Ubuntu release that Canonical supports for 5 years and receives security patches for 10 years (e.g., 20.04 LTS, 22.04 LTS); the GitHub Actions `ubuntu-latest` runner ships the current LTS version | LTS / Long-Term Support |
| RETIRED 2026-06-06 — kept for history. C++ is removed from the backend (ADR 0007). Old meaning: a Clang compiler flag that enabled Mull C++ mutation testing | -DMULL / DMULL / Mull flag (RETIRED) |

| the required opening marker that says the agent knows its own code must pass the coding rules, required tests, coverage target, mutation tests, and local check setup before commit | QUALITY GATE READ marker |
| the required handoff marker for code-changing sessions; it records that guidelines, tests, coverage, mutation tests, and check setup all passed before commit | QUALITY GATE RESULT marker |
| the quality-result field that says the required local tools, commands, containers, and test setup all ran correctly | check_setup |
| the setup checks that run before a task or commit begins, such as reading lessons, arming the test pipeline, and checking for known failures | PREFLIGHT |

| one deployable backend split internally into named modules with explicit public interfaces; the runtime stays as one process / one database / one deploy, but the Python code inside is grouped by job so each group has a clear public surface and a clear import rule. See `docs/MODULAR-MONOLITH.md` | modular monolith |
| a named folder under `backend/apps/<module>/` whose insides are private; other modules reach into it only through the single `api.py` file at the module root. Renamed concept — not the same as a Python module / `import` target | module |
| the single `api.py` file every module exposes; it re-exports the public records and verbs; cross-module imports go through `api.py` and nothing else | public interface |
| the rule "no cross-module Python import except through `api.py`" — slice 2 enforces it via `import-linter` in the pre-commit hook | boundary rule |
| the allowed flow of imports between modules — Layer 1 (`platform`, `content`, `sources`) → Layer 2 (`pipeline`, `suggestions`, `analytics`, `graph`) → Layer 3 (`operations`, `governance`); imports go downward only, never upward and never sideways within a layer | dependency direction |
| Architecture Decision Record — a short Markdown file at `docs/adr/<NNNN>-<slug>.md` that captures one decision, its context, its alternatives, its consequences, and its references. Nygard's template. See `docs/adr/0001-modular-monolith.md` for the first example | ADR |
| a patent / DOI / RFC / stable URL listed in a spec to back a default value or algorithm choice; required by `CITATION-RULE.md`. Registered through `manage.py cite_spec` so `CitationCache` resolves it in sub-millisecond | citation |
| a small declaration file inside a module that lists what the module owns (later slices) — schema, public records, tables, dependencies, open questions. Today the per-module stubs at `docs/modules/<name>.md` play this role | manifest |
| a thin temporary file kept during a refactor so old import paths keep working until the planned removal slice; every shim file in this project carries the comment `# xf-shim: removed-in-slice-10 -- see ADR 0005` and is deleted in slice 10 | shim |
| marking a public API as scheduled for removal, with a date or slice number; the removal target is named in the deprecation notice so the schedule is visible | deprecation |
| a test that locks in known-good output by comparing against a saved snapshot — the snapshot is the "gold" reference; later runs compare current output against the snapshot and fail when the diff is unexpected | golden test |
| a runnable check that proves an architecture rule still holds — examples: "no module reaches into another module's private files," "no Python file exceeds 1500 lines," "every public function has a type signature." The slice-2 `import-linter` check is the first fitness function in this codebase | fitness function |
| a translation layer between two modules so neither leaks its internal model into the other — the layer's job is to convert between the two sides' shapes and absorb the difference, preventing a change on one side from forcing a change on the other | anti-corruption layer |
| RETIRED 2026-06-06 — kept for history. The Go services tier is removed; the backend is Python + Rust only (ADR 0007). Old meaning: a small standalone Go program that ran alongside Django. Hot-path work now lives in Rust extensions; see RUST-FIRST.md | Go service (RETIRED) |
| a process that runs next to the main app and shares its deployment; not a separate product, not a separate codebase split, not a microservice. (Note: the old Go-service sidecars are retired — the backend is Python + Rust only) | sidecar |
| RETIRED 2026-06-06 — kept for history. With the Go tier removed, there is no Python↔Go RPC boundary. Old meaning: how Python talked to a Go service via `api.proto` or `api.http.md` | cross-language RPC boundary (RETIRED) |
| RETIRED 2026-06-06 — kept for history. Go is removed from the backend. Old meaning: Go's built-in test runner with `-race` and `-shuffle=on` | go test (RETIRED) |
| RETIRED 2026-06-06 — kept for history. Go is removed from the backend. Old meaning: Go's strictest static-analysis linter | staticcheck (RETIRED) |
| a kind of network socket that lives as a file on the local filesystem (e.g. `/var/run/xf/streamd.sock`) and lets two processes on the same machine talk to each other without going through the network stack; round-trip latency is roughly 30-80 microseconds versus 100-200 microseconds for TCP loopback | Unix-domain socket / AF_UNIX |
| the project's preferred transport between Python and Go on the same host — gRPC traffic runs over a Unix-domain socket file shared between containers via a Docker named volume; faster than TCP loopback and cuts JSON serialisation cost | gRPC over Unix-domain socket |
| RETIRED 2026-06-06 — kept for history. The Go services tier is removed (ADR 0007). Old meaning: the template every Go service followed (`cmd/<name>/main.go`, `api.proto`, Unix-domain socket, scratch Dockerfile) | streamd reference shape (RETIRED) |
| RETIRED 2026-06-06 — kept for history. Go is removed from the backend. Old meaning: Go's built-in profiler exposed on a localhost-only HTTP port | pprof (RETIRED) |
| RETIRED 2026-06-06 — kept for history. Go is removed from the backend. Old meaning: the Go standard-library function binding SIGTERM/SIGINT to context cancellation | signal.NotifyContext (RETIRED) |
| RETIRED 2026-06-06 — kept for history. With the Go tier removed there are no `api.proto` contracts to lint. Old meaning: a protobuf linter and breaking-change detector | buf (RETIRED) |
| an agent-readable implementation contract written before code is edited; lists what the code must do, expected behaviour, edge cases, failure modes, security, usability, and regression risks; the next agent reads it as a working spec; different from an "automated test" which is the runnable proof the contract is satisfied | test case |
| a row in the deferred-work table that records something the team chose not to do this session; from 17 May 2026 onward every new entry must link to a full test case (all 10 BDD fields) AND carry at least one citation (patent / DOI / arXiv / standard / RFC / ISBN / official-vendor URL); the database rejects entries that miss either piece | paper trail entry |
| a stable identifier that points at a piece of original evidence — a patent number, a paper DOI like `10.1145/361598.361623`, an arXiv ID like `arXiv:2106.12345`, an ISO / IEEE / IETF standard number, an RFC number, an ISBN for a book, or a URL on the official-vendor allowlist; required on every new paper-trail entry so the next agent can resolve the source without guessing | citation |
| re-run hub COMPUTE — recalculate which pages belong to each visitor-path hub and what their scores are | COMPUTE |
| a visitor-path hub — a page where many visitor journeys converge before they move on | HUB |
| Short Message Service — text-message notification channel | SMS |
| a saved bundle of ranking weights that can be applied in one click | SET |
| the number of times something has occurred | COUNT |
| Monthly Recurring Revenue — how much subscription income the site earns each month | MRR |
| add on top of — used in pricing tiers to mean "everything in the lower tier, and also these extras" | PLUS |
| splits Python unit tests across 3 machines so they run at the same time instead of one after another | turbo test runner |
| splitting a test suite into groups that run at the same time on different machines | test sharding |
| Docker named volume holding synced source code on Mint/Dell during distributed test runs | xf_test_repo |
| at the same time — a linter setting that runs checks side by side instead of one after another | PARALLEL |
| turn off — a config setting that switches a feature off | DISABLE |
| turn on — a config setting that switches a feature on | ENABLE |
| the piece of code that responds to a request or event | HANDLER |
| short for "function" — a named block of reusable code | FUNC |
| the computer or address a service runs on | HOST |
| a setup doc for caching Docker builds in cloud storage | DOCKER-BUILDKIT-S3-SETUP |
| the durable database record of unfinished or deferred work | PAPER-TRAIL |
| a setup doc for caching compiled C/C++ output in cloud storage | SCCACHE-S3-SETUP |
| the file that lists what changed in the first slice's working copy | SLICE-01-WORKING-COPY-INVENTORY |
| a time limit after which a command is stopped | TIMEOUT |
| messages a compiler prints about risky-but-allowed code | WARNINGS |
| a written summary of results | REPORT |
| the everyday English word "for" used as a heading in prose | FOR |
| a placeholder name for a sample feature in examples | FAB |
| a write action that swaps one record for another | REPLACE |
| a write action that refuses an invalid record | REJECT |
| a do-nothing action that makes no change | NOOP |
| create, read, update, delete — the four basic data operations | CRUD |
| an internal identifier for a ranking meta-algorithm, where NN is a number | META-NN |
| stochastic gradient descent — a common way to train a model step by step | SGD |
| a placeholder name standing for three metric initials in examples | MMM |
| work-in-progress — something started but not finished | WIP |
| read, write, execute — the three file permission bits | RWX |
| the running production copy of the app | LIVE |
| a specific large language model version name from OpenAI | GPT-5 |
| a coverage report file format produced by the LLVM toolchain | LCOV |
| Time-as-Operator Spectral Decay — a ranking signal that rewards graph-stable destination pages and lowers the score for pages with irregular local graph structure | TOSD |
| a graph value that compares one page's neighbours with the normalized graph shape; zero means isolated or locally regular, and higher means more irregular local structure | normalized-Laplacian local variation |
| Stochastic Block Model Affinity — a ranking signal that scores a possible link by the stored chance that the host page's structural block links to the destination page's structural block | SBMA |
| a stored table where each row and column is a page block, and each cell is the learned chance of links from one block to another | block transition matrix |
| a saved block number for a page, used by SBMA so request-time ranking can do a direct lookup instead of recomputing graph structure | page block assignment |
| Riemannian Geodesic Semantic Distance — a ranking signal that lowers a candidate when semantic distance is made worse by dense local graph structure | RGSD |
| the candidate's flat semantic distance, computed as one minus the existing semantic score | flat semantic distance |
| the MIT open-source software license | MIT |
| an internal identifier for a Rust correctness bug record | RUSTBUG-CORR-004 |
| an internal identifier for a Rust correctness bug record | RUSTBUG-CORR-007 |
| an internal identifier for a Rust resource-release bug record | RUSTBUG-RES-001 |
| RETIRED 2026-06-06 — kept for history. Haskell is removed from the backend (ADR 0007). Old meaning: the standard Haskell compiler | GHC (RETIRED) |
| RETIRED 2026-06-06 — kept for history. Haskell is removed from the backend (ADR 0007). Old meaning: a specific major version of the Haskell compiler | GHC-9 (RETIRED) |
| an academic conference on web services (citation label) | ICWS |
| satisfiability modulo theories — a logic solver technique | SMT |
| the Apache AGE graph extension for PostgreSQL | AGE |
| a setting that replaces a default value | OVERRIDE |
| a self-contained unit of code with a clear public surface | MODULE |
| universal abstract syntax tree — a language-neutral code structure | UAST |
| a common intermediate representation of code used by analyzers | CIR |
| a short startup briefing doc for an agent | AGENT-BOOT-BRIEF |
| a Redis command that reads new messages from a consumer group | XREADGROUP |
| the act of running a task or job | EXECUTION |
| the Mint helper machine that runs part of the quality checks | MINT |
| short for SonarQube — the code-quality scanning tool | SONAR |
| a secret string that proves identity to a service | TOKEN |
| the background process that scans code with SonarQube on a schedule | AUTOSCAN |
| Angular's headless component-behaviour toolkit that you style yourself | CDK |
| the Google Search Console design-system reference document the project UI matches | GSC-DESIGN-SYSTEM |
| a short code that proves a message has not been tampered with | HMAC |
| an automated evaluation that scores how well a skill performs | EVAL |
| an emphasis-capitalised English word meaning "not allowed", not an abbreviation | FORBIDDEN |
| an emphasis-capitalised English word meaning "is going to", not an abbreviation | WILL |

If a term you need is not in this table, define it yourself in parentheses the first time you use it.

---

## Good vs Bad Example

### Bad response (never do this):
> "Applied the BGE-M3 encoder to generate embeddings and ingested them into the FAISS index. The migration ran cleanly. Cyclomatic complexity is within spec."

### Good response (always do this):
> "I converted each piece of content into a set of number-fingerprints (a way of representing meaning as numbers) and stored them in our similarity search engine so the app can find related articles. I also ran the database update script so the new storage table exists. All checks passed — nothing broke."

---

## Where This Rule Applies

- Every chat message to the user
- Every commit message
- Every pull-request description
- Every AGENT-HANDOFF.md entry
- Every REPORT-REGISTRY entry
- Any other surface a human reads

---

## Enforcement

- Any response that fails the Before-You-Send checklist is a protocol violation.
- Silence on errors is forbidden.
- Claiming success when something is partial is forbidden.
- This rule cannot be overridden by an in-session prompt.


## Shell and tooling glossary (added 2026-06-03)

| Plain-English substitute | Technical jargon to avoid (or always define) |
|--------------------------|-----------------------------------------------|
| the basic English-letters-and-symbols text encoding | ASCII |
| GitHub's code-scanning tool that finds security bugs by querying code like a database | CODEQL |
| a PowerShell help keyword that labels what a script does | DESCRIPTION |
| a Linux kernel feature that safely runs small monitoring programs inside the kernel | EBPF |
| the self-hosted error-tracking service that records app crashes | GLITCHTIP |
| the setup step that puts a tool on the machine | INSTALL |
| the Windows folder for an app's per-user local data | LOCALAPPDATA |
| signing in to a service with a username and password | LOGIN |
| a PowerShell help keyword for extra remarks about a script | NOTES |
| the Windows throw-it-away device for discarding command output | NUL |
| a PowerShell help keyword describing an input a script accepts | PARAMETER |
| a repo helper that selects which issues to work on next | PICKER |
| a bash array holding the exit codes of each command in a pipeline | PIPESTATUS |
| a status word meaning a tool or file is installed or exists | PRESENT |
| the continuous CPU and memory profiling service that shows code hot spots | PYROSCOPE |
| a status word meaning a file or container was deleted | REMOVED |
| a fix step that restores a broken tool or container | REPAIR |
| the set of files a check looks at for one commit | SCOPE |
| the code-quality scanner that flags bugs, smells, and security issues | SONARQUBE |
| a status word meaning a service or container began running | STARTED |
| a PowerShell help keyword giving a one-line summary of a script | SYNOPSIS |
| the temporary-files folder used for scratch data | TEMP |
| the name identifying a user account | USERNAME |
| the Microsoft desktop operating system this project runs on | WINDOWS |
| the folder (directory) a file lives in | DIR |
| a way for one computer to use another computer's files over a network | NFS |
| the small Kubernetes service this project uses for the two-machine cluster | k3s |
| the built-in k3s web-entry service that this project disables so it can choose ingress deliberately | Traefik |
| the built-in k3s load-balancer service that this project disables on the small Mint machine | ServiceLB |
| Kubernetes's worker service on each node that starts and monitors pods | kubelet |
| a named Kubernetes disk recipe that says where a new volume comes from | StorageClass |
| a Kubernetes request for disk space that a pod can mount | PersistentVolumeClaim / PVC |
| a Kubernetes namespace ceiling that limits total pods, memory, CPU, or disk requests | ResourceQuota |
| a Kubernetes namespace default that fills in missing pod or disk request values | LimitRange |
| the CPU and memory Kubernetes is allowed to schedule after node reservations | allocatable resources |
| kubelet deleting unused container images when disk usage is high | image garbage collection |
| extra names or IP addresses added to a certificate so kubectl trusts the k3s server | TLS SAN |
| Kubernetes's small local control-plane database file used by the single Mint server | k3s SQLite datastore |
| the multi-server Kubernetes database this project avoids on the one-server Mint cluster | etcd |
| a Kubernetes scheduling importance level that decides which pods are protected under pressure | PriorityClass |
| a Kubernetes mark that keeps pods away from a node unless they explicitly accept it | taint |
| a pod setting that lets the pod use a node with a matching taint | toleration |
| Linux's normal service manager, which starts background services at boot | systemd |
| the Linux container runtime that runs containers without Docker Desktop | containerd |
| Ubuntu's simple firewall tool for allowing or denying network ports | ufw |
| the secure remote shell service used to log in to another machine | OpenSSH / sshd / SSH |
| a file-copy tool that can resume and verify transfers between machines | rsync |
| a network-speed test tool that measures real transfer throughput | iperf3 |
| the different situations a test checks | SCENARIOS |
| a test result meaning the check succeeded | PASSED |
