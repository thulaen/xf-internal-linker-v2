# Plain-English Communication Rule

**This rule applies to every AI agent that works in this repository: Claude, Codex, Gemini, Antigravity, and every future agent. It is non-negotiable.**

---

## The Rule in One Sentence

Every word you send to the user must be understandable by someone who has never written a line of code in their life.

---

## PARAMOUNT — Plain-English Communication Rule

Every response, commit message, error report, status update, and user-facing surface MUST be written in plain English the user can understand. The user is a vibe coder — they use AI exclusively and don't write code.

**Every substantive response must contain all three of these parts:**

1. **What I'm doing / will do** — describe the action in everyday words. Define every technical term the moment it first appears. No unexplained acronyms (FR-XXX, ISS-XXX, RPT-XXX, MMR, BGE-M3, FAISS, RSQVA, PPR, HITS, HGTE, etc.).

2. **What was accomplished** — at the end of every change, state in plain English what now works that didn't before, plus which files changed and why.

3. **What has issues or errors** — surface failures honestly. If something broke, say what broke, why, and what you'll do about it. Never bury errors in jargon. Never silently move on. Never claim success when something is partial. If a step was skipped, say so.

Skipping any of the three parts is a protocol violation. Silence on errors is forbidden.

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

- **Flesch Reading Ease: 60 or higher.** Below 60 the text is in the "fairly difficult" band.
- **Flesch-Kincaid Grade Level: 9 or lower.** A 9th grader should be able to read it.
- **Passive sentences: 10 percent or lower.** Active voice is shorter and clearer.

The agent does not need to run a tool on every response. The targets are the standard the writing must aim at. Common drift to watch for: long sentences with multiple clauses, passive voice ("was caught by"), and dependent-clause stacking.

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
| a speed-boosted module written in a faster language (C++) | C++ extension |
| the background task runner | celery worker |
| the framework that builds the visual interface | Angular |
| the framework that handles data storage and business logic | Django |
| a packaging system that makes the app run the same everywhere | Docker |
| a Dockerfile line that sets a value the container can read while it runs | ENV |
| a Dockerfile line that sets the folder future commands run from | WORKDIR |
| a Dockerfile line that sets the default command for the container | CMD |
| the repo rule file that explains how Docker builds and stores compiled-language outputs | COMPILED-LANGUAGE-RULES |
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
| the standard way modern AI agents call external tools | MCP / Model Context Protocol |
| Anthropic's local AI coding agent that runs in your terminal | Claude Code |
| OpenAI's local AI coding agent that runs in your terminal | Codex / Codex CLI |
| Google's local AI coding agent that runs in your terminal | Antigravity |
| Anthropic's monthly subscription that includes Claude Code | Max 5x |
| a long string the app uses to prove it's allowed to call its own backend | Django Token |
| running an AI agent without a chat window — give it one prompt, take its answer | headless mode |
| a single number that combines several scoring factors into one final ranking number | composite score |
| a Go test tool that makes small deliberate code changes and checks that the tests catch them | go-mutesting |
| a tag we put on a link suggestion to mark it as picked but not yet applied | proposed |
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
| a separate Docker container that runs alongside the main app | service / sidecar service |
| a config file at the project's root that AI agents auto-discover | .mcp.json / project-scope MCP config |
| numbered "feature request" specs in `docs/specs/fr*.md` — each one a contract for a feature | FR-014 / FR-016 / FR-XXX (any 3-digit feature number) |
| FR-250 — a small C++ helper that holds back outbound API calls so we never go faster than each provider's documented limit (Google Search Console, Google Analytics 4, Matomo, XenForo, WordPress) | FR-250 / API rate limiter |
| a way to compress number-fingerprints so the similarity search engine can fit a giant index in memory by storing each vector as a tiny code instead of a full float array | OPQ / Optimised Product Quantization |
| an embedding model that turns text into number-fingerprints — the project's default | BGE-M3 |
| Beijing Academy of Artificial Intelligence — the research org that publishes the BGE-M3 embedding model used as the project default | BAAI |
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
| the standalone autotuner that adjusts meta-algorithm parameters (RRF k, BM25 k1/b, MMR lambda, etc.) on a monthly schedule with the same challenger-escrow safety as the ranking-weight tuner | meta-algorithm autotuner / FR-018b |
| a security hole that lets an attacker run arbitrary code on the server — e.g. by feeding a malicious pickled blob into a `pickle.loads` call | RCE / Remote Code Execution |
| a stable, permanent identifier for an academic paper or other digital document — looks like `10.1145/1571941.1572114`; the prefix `10.` is what marks it as a DOI | DOI / Digital Object Identifier |
| a fast table-of-data library written in Rust — like a spreadsheet you can drive from Python, but it uses every CPU core automatically; the project uses it to add up millions of analytics rows in seconds instead of minutes | Polars |
| a table of data with named columns, like a single sheet in a spreadsheet — Polars and pandas both work in DataFrames | DataFrame |
| sorting rows into buckets by a column (e.g. by suggestion ID) and then adding up the values inside each bucket — the standard way to roll up raw events into per-thing totals | groupby / aggregate |
| a small, fast file format for tabular data — stores columns separately so reading just one column is much quicker than CSV; used by Polars and pyarrow for weekly model snapshots on disk | Parquet |
| a measure of statistical spread that shrugs off outliers — equals the median of the absolute differences from the median; the project uses it to decide which anchor texts are unusually rare or unusually common | MAD / median absolute deviation |
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
| an industry framework for running an IT department — defines vocabulary like "incident", "problem", "change request" the way a hospital defines "triage"; the C++ daily picker spec borrows ITIL severity levels | ITIL / IT Infrastructure Library |
| the public ID for a known security flaw — looks like `CVE-2024-12345`; `pip-audit` checks the project's installed packages against this database every night | CVE / Common Vulnerabilities and Exposures |
| the 0–10 score that says how bad a CVE is — 0 trivial, 10 game-over; the auto-issues priority formula multiplies CVSS by recency and blast-radius | CVSS / Common Vulnerability Scoring System |
| GitHub's own security-advisory database — an alternative ID for vulnerabilities (`GHSA-xxxx-xxxx-xxxx`); pip-audit reports both CVE and GHSA when both are assigned | GHSA / GitHub Security Advisory |
| a Web Vital metric that measures how long the page takes to react after the user clicks/taps — replaced FID in 2024 as the standard responsiveness yardstick | INP / Interaction-to-Next-Paint |
| the legacy responsiveness Web Vital — measured the delay between a click and the browser starting to handle it; replaced by INP | FID / First Input Delay |
| Microsoft's Visual C++ compiler — the C++ toolchain used when building native extensions on Windows; produces `.exe`, `.lib`, `.exp`, and `.pdb` byproducts the benchmark runner has to filter out | MSVC / Microsoft Visual C++ |
| the four scoring components inside the C++ daily picker — Severity (how bad), Recency (how new), Regression (was-fine-yesterday), and Akaike Information Criterion (penalty for touching many modules); blended into one priority score per issue | SEV / REC / REG / AIC |
| the international rulebook for making websites usable by people with disabilities — covers things like keyboard navigation, screen-reader support, color contrast; "AA" is the middle compliance level most enterprises target | WCAG / Web Content Accessibility Guidelines |
| the JavaScript view of CSS — every loaded stylesheet exposes a `cssRules` array the browser keeps in sync; we walk it to debug why a CSS rule isn't winning the cascade | CSSOM / CSS Object Model |
| the standard file format for translation work — an XML file with one entry per source string and a `<target>` slot the translator fills in; produced by `ng extract-i18n` and consumed by `ng build --localize` | XLF / XLIFF / XML Localization Interchange File Format |
| the old session-start rule that required three AutoIssue fixes before new work; this wording is historical only and is forbidden in new handoff entries because the current rule requires 30 real AutoIssue fixes | auto-fix-3 / auto-fix-3 satisfier / fix three before any new task |
| a database row that records one bug, test failure, missing check, or code-quality problem for agents to fix later | AutoIssue / AUTOISSUE |
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
| Foreign Function Interface — the boundary where Python calls into C++ (via pybind11) or vice-versa; used in the project's hot-path rerankers so the slow Python ranking math is replaced by fast C++ kernels | FFI |
| Near-Real-Time — describes scoring or retrieval that happens within seconds of an event (vs. batch jobs that run nightly); the project's NRT signals power live confidence-meter updates and the autotuner's short-window feedback loop | NRT || pre-commit hook script at `.githooks/check-file-size.py` that blocks commits adding a file over 1,500 lines (the cap from CLAUDE.md), and prevents grandfathered files (listed in `.githooks/file-size-grandfather.txt`) from growing past their recorded baseline | check-file-size / file-size-grandfather |
| pre-commit hook script at `.githooks/check-no-downgraded-gates.py` that blocks any commit which silently flips a CI gate from blocking to warning-only (`\|\| true`, `continue-on-error: true`, `exit-code: '0'`, `::warning::`) unless the same diff also adds a `# GATE-DOWNGRADE-JUSTIFICATION:` comment with a real reason | check-no-downgraded-gates / GATE-DOWNGRADE-JUSTIFICATION |
| pre-commit hook script at `.githooks/check-frontend-routes.py` that scans every `HttpClient.get/post/put/patch/delete('/api/...')` call in staged frontend TypeScript files and verifies the URL resolves to a real `path('...')` declaration in `backend/apps/**/urls.py`; prevents stale frontend → backend URL drift | check-frontend-routes |
| pre-commit hook script at `.githooks/check-missing-tests.py` that blocks commits which add a new `*.component.ts`, `*.service.ts`, or `backend/apps/*/services/*.py` file without a matching test file (sibling `.spec.ts` for frontend, `test_<base>.py` in same/parent/tests dir for backend) | check-missing-tests |
| AddressSanitizer — a Clang/GCC compiler instrumentation that catches memory-corruption bugs (use-after-free, out-of-bounds reads/writes, double-free, leaks) at runtime; the project runs the C++ extensions under it in CI to catch native-code bugs the unit tests would miss | ASAN / AddressSanitizer |
| ThreadSanitizer — sister to ASAN that catches data races and thread-safety bugs at runtime; the project's CI build runs C++ tests under TSAN but the gate is currently advisory because TBB produces false positives that need a curated suppression file | TSAN / ThreadSanitizer |
| Intel Threading Building Blocks — the C++ task-stealing scheduler the project's hot-path C++ kernels use for parallel work; TBB internals trigger false-positive TSAN warnings under its work-stealing scheduler, which is why TSAN stays advisory until a suppression file is curated | TBB |
| log database — stores every container's stdout line, queryable like a search engine; runs default-on alongside GlitchTip and Pyroscope; reachable at `localhost:3100`; 30-day retention | Loki |
| log shipper — a small agent that watches every running container's stdout and forwards each new line to Loki; runs default-on as the `alloy` service; replaces Promtail (which Grafana retired in March 2026) | Grafana Alloy / Alloy |
| log query language — the search syntax for Loki; example: `rate({container_name="xf_linker_backend"} \|~ "(?i)error" [5m])` says "errors per second in the backend container over the last 5 minutes" | LogQL |
| Alloy's configuration language — looks like HCL/Terraform; defines pipelines as nested blocks (`discovery.docker "containers" { ... }` then `loki.source.docker "all" { ... }`); the project's pipeline lives in `config.alloy` at the repo root | River |
| retired log shipper — Grafana's original Loki agent; entered maintenance-only mode 2026-03-02; this project never adopted it, jumping straight to Alloy | Promtail |
| OpenTelemetry collector container — the OTel pipeline hub the project still uses for traces and metrics (Alloy lacks the Sentry-format exporter that GlitchTip needs, so otel-collector stays); reads OTLP from the backend + Celery, fans out to GlitchTip + Prometheus + stdout | otel-collector |
| OpenTelemetry Protocol — the wire format every modern tracing/metrics tool speaks; the backend pushes OTLP over HTTP at port 4318 to otel-collector | OTLP |
| auto-issues table — the Django table at `apps.auto_issues.AutoIssue` where every automated finding lands so agents can read them at session start via `manage.py print_open_issues`; sources are `agent`, `glitchtip`, `pyroscope`, `loki` | AutoIssue |
| same-day CPU bottleneck check — Pyroscope picker that ranks functions by self-time over the last hour and files an AutoIssue for any function above a percentage threshold; works from day one (no week-of-history required) | hotspot detector / pyroscope hotspot |
| repeated-warning detector — Loki picker that groups WARN/ERROR lines by normalized fingerprint (timestamps, PIDs, hex addresses stripped) and files an AutoIssue when one pattern occurs many times in 24 h | hot pattern detector / loki hot pattern |
| short-window WARN/ERROR rate spike — Loki picker that compares the last hour's WARN/ERROR count to the 24-hour average and files an AutoIssue when the multiple is high | warn burst / loki warn_burst |
| placeholder AutoIssue filed when an automated source produced fewer findings than the session-start ritual expects (e.g. Loki has only 2 hot patterns instead of 4); the next agent investigates why the source was empty | picker_drought |
| structured-analysis output format — the standard JSON file every code-quality / security scanner writes (Static Analysis Results Interchange Format); the project does not currently emit SARIF but it would be the wire format if a Qodana / Semgrep importer is ever added | SARIF |
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
| the Python mutation-testing tool used by this project (scope: `apps/auto_issues/services/fingerprinting.py`). Invoked via `mutmut run --paths-to-mutate=<path> --runner=<test cmd>`; `mutmut results` exits non-zero if any mutant survived | mutmut |
| the TypeScript / Angular mutation-testing tool used by this project (scope: `frontend/src/app/core/services/a11y-prefs.service.ts`). Reads `frontend/stryker.config.json`; integrates with Karma so the existing test runner mutates each file in turn | Stryker / Stryker Mutator |
| the C++ mutation-testing tool used by this project (scaffold only — needs a Mull-compatible Clang toolchain). Reads `mull.yml`; injects mutations at the LLVM IR level which is orders of magnitude faster than source-level mutation for C++ | Mull |
| one specific edit rule a mutation tool can apply (e.g. `cxx_relational_replacement` swaps `<` and `>`; `arithmetic_replacement` swaps `+` and `-`). The mutation tool walks the source once per mutator and tries each rule at every applicable location | mutator (mutation-testing sense) |
| LLVM is an open-source compiler infrastructure project that the Clang C/C++ compiler is built on; tools like Mull, libFuzzer, ASan/TSan/MSan, and clang-tidy all ship as LLVM components. When the docs say "Mull works at the LLVM IR level," they mean it edits the intermediate code Clang produces before machine-code emission | LLVM |
| coverage-guided random-input fuzz tool that ships with LLVM/Clang — feeds randomly-mutated byte arrays at thousands per second into a `LLVMFuzzerTestOneInput(uint8_t*, size_t)` function and watches whether the code crashes, leaks memory, or trips a sanitizer. Paired with `-fsanitize=fuzzer,address` so every interesting bug becomes a non-zero exit. Starter targets in `backend/extensions/fuzz/`; authoring guide in `AUTHORING.md` | libFuzzer |
| MemorySanitizer — Clang sanitizer that catches reads of uninitialised memory at runtime (e.g. `int x; if (x > 0) {...}`). Highest false-positive rate of the sanitizers because it needs every dependency rebuilt with MSan instrumentation to avoid noise; this project ships a **project-only** MSan with `-fsanitize-blacklist=backend/extensions/msan-ignore.txt` excluding Faiss / Eigen / ICU / TBB / pybind11 | MSan / MemorySanitizer |
| a libFuzzer harness file — one `LLVMFuzzerTestOneInput()` function that interprets a fuzz-generated byte stream as input to one C++ function under test. Lives in `backend/extensions/fuzz/fuzz_<name>.cpp`; rebuilt every CI run; smoke-runs for 60s per target | fuzz target |
| the directory of seed inputs libFuzzer starts from when fuzzing a target (one dir per target under `backend/extensions/fuzz/corpus/<name>/`); libFuzzer mutates these and adds new "interesting" inputs that explore previously-unvisited code paths. Crash-reproducer files (`crash-<sha1>`) drop into the same dir | fuzz corpus / seed corpus |
| Clang's per-sanitizer "ignore this file/function/source-path" config — used in `backend/extensions/msan-ignore.txt` to tell MSan not to flag reads originating inside Faiss / Eigen / ICU; reads from blacklisted code are treated as initialised. Format: `src:*/faiss/*`, `fun:Py*`, etc. | sanitizer blacklist / -fsanitize-blacklist |
| contract-testing framework — the Angular frontend declares "I will call POST /api/foo with {a,b} and expect {c,d} back"; that contract is saved as a JSON file; the Django backend then has a test that replays each declared interaction and fails the build if the response shape drifts. Catches frontend/backend desync at PR time | Pact / contract testing |
| the central registry server that holds every Pact JSON file (one consumer + one provider + their negotiated contract version). Lives in `docker-compose.yml` under the dev profile when used; the in-repo workflow can also just commit the JSON files directly and skip the broker for simpler one-team cases | Pact broker |
| the discipline of letting the consumer (Angular) define the contract, then making the provider (Django) prove it conforms. The opposite is "provider-driven" where the backend ships an OpenAPI / Swagger spec and consumers adapt — Pact prefers consumer-driven because it makes the consumer's actual usage the source of truth, not a hand-edited spec that can drift | consumer-driven contracts |
| meta-linter — Super-Linter is a single GitHub Action that bundles ~50 different linters (Hadolint, golangci-lint, markdown-lint, yaml-lint, gitleaks, etc.). The project uses it for the linters we don't already run as dedicated jobs (Ruff and ESLint stay separate to avoid duplicate version-pinning) | Super-Linter |
| Hadolint — Dockerfile linter (catches use of `ADD` instead of `COPY`, unpinned base images, `apt-get install` without `--no-install-recommends`, etc.). Runs inside Super-Linter on every PR via `VALIDATE_DOCKERFILE_HADOLINT=true` | Hadolint |
| Gitleaks — secret-scanner that flags API keys, AWS access tokens, private keys, etc. accidentally committed to git history. Runs inside Super-Linter on every PR via `VALIDATE_GITLEAKS=true` | Gitleaks |
| the third required ritual marker line (Phase 7) — proves the agent ran `gh run list --status failure --limit 10` at session start and reviewed the 10 latest failed GitHub Actions workflow runs. Two valid forms: `[CI FAILED RUNS READ: <N> latest — picked: #<id>, ...]` (populated) or `[CI FAILED RUNS READ: skipped — gh unavailable]` (when the gh CLI isn't installed). `.githooks/check-registry-read.py` enforces presence. | CI FAILED RUNS READ marker |
| the PARAMOUNT rule added 2026-05-12 — after writing any code, every agent must run the relevant random-order test suite, read failure output, fix the cause, and re-run until the exit code is zero. Applies to pytest / ng test / ctest invocations equally; the pre-push hook running mutmut / Stryker / libFuzzer / clang-tidy on changed files only counts under the same rule. Silently moving on is a protocol violation | auto-iterate after writing code |
| the project's comprehensive coding rules file at `AI-CODING-GUIDELINES.md` (repo root). Every agent reads it at session start, before every task; it defines the prime directive, source-of-truth order, no-hallucination rules, work loop, code-smell + long-function + bug-fix + test-requirement + property-based + evidence-based + business-logic + state-transition + idempotency + database + error + logging + security + external-service + performance + paid-API + naming + dependency + formatting + type-safety + UI + accessibility + concurrency + refactoring + generated-code + file-editing + test-running rules + Definition of Done + the per-task coverage target table | AI-CODING-GUIDELINES.md / coding guidelines |
| the strict coverage rules file at `docs/CODE-COVERAGE-RULES.md`. Defines Level A/B/C/D, the 14 Level A areas (import normalization / text cleaning / sentence splitting / embedding lifecycle / index build/search / scoring / meta-algo / business logic / near-dup removal / existing-link detection / broken-link detection / approval transitions / permissions / analytics import + Celery idempotency + DB integrity), per-language floors (backend 90%, API 90%, Celery 90%, Angular 75%, C++ 100% branch + Mull ≥70%), property-test invariant menus, drought clause | docs/CODE-COVERAGE-RULES.md / coverage rules |
| the strictest coverage tier in `docs/CODE-COVERAGE-RULES.md` — Modified Condition/Decision Coverage (MC/DC), 100% line + branch coverage, property-based tests, mutation testing, golden-fixture regression tests, end-to-end review-workflow tests, traceability of each test to a rule / FR / invariant. Applied to anything touching business logic, scoring, parsing, security, or financial decisions | Level A / MC/DC coverage |
| Modified Condition/Decision Coverage — DO-178C / NASA NPR 7150.2D structural coverage tier where every Boolean condition in every decision is independently exercised showing it can affect the outcome. The strongest commonly-used coverage criterion; required for Class A / safety-critical software | MC/DC / Modified Condition Decision Coverage |
| an AutoIssue row that flags a missing or insufficient test for a specific Level A area or per-language target. Title begins with `[coverage-gap]`. Source = `agent`. Drained at 10 per session via the standard opening ritual; backlog seeded by FR-251 | coverage-gap AutoIssue |
| the fourth required ritual marker (FR-251) — proves the agent read both `AI-CODING-GUIDELINES.md` and `docs/CODE-COVERAGE-RULES.md` at session start. Exact form: `[GUIDELINES READ: AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]`. `.githooks/check-registry-read.py` enforces presence | GUIDELINES READ marker |
| the fifth required ritual marker (FR-251) — proves the agent picked 10 coverage-gap AutoIssues to drain this session alongside the standard 18 auto-issue picks and 10 latest failed CI runs. Two valid forms: `[COVERAGE GAPS READ: 10 picked — #..., ...]` (populated) or `[COVERAGE GAPS READ: <K> picked + <10-K> to file — #..., (drought; ...)]` (drought) | COVERAGE GAPS READ marker |
| the end-of-slice / end-of-task / end-of-session honesty marker (FR-251) — `[COVERAGE SUMMARY: target=<X>% actual=<Y>% — met / not met — <reason if not met>]`. Honesty is mandatory; claiming "met" when the suite is red is a protocol violation | COVERAGE SUMMARY marker |
| FR-251 — the FR spec governing the strict code-coverage program shipped 2026-05-12. Sets the rules in `AI-CODING-GUIDELINES.md` + `docs/CODE-COVERAGE-RULES.md`; the actual work to achieve the targets lives in ~23 coverage-gap AutoIssues drained 10-per-session. See `docs/specs/fr251-code-coverage-program.md` | FR-251 / code-coverage program |
| a fuzz-coverage-gap AutoIssue — one per public C++ module in `backend/extensions/` without a matching `fuzz_<name>.cpp` target. Emitted by `apps.auto_issues.services.fuzz.pick_fuzz_coverage_gaps`. The libFuzzer ratchet — as fuzz targets are added per the AutoIssue queue, these gap rows resolve | fuzz-coverage-gap |
| an object-oriented design principle that says "only talk to your immediate friends" — a method should only call methods on (a) itself, (b) its parameters, (c) objects it creates locally, (d) its direct component objects. Forbids deep chains like `a.b().c().d()`. Encourages "tell don't ask" redesigns where the caller's friend exposes a method that returns the needed value directly. See `AI-CODING-GUIDELINES.md` § Design principles | Law of Demeter / LoD |
| a design principle that each module owns exactly one responsibility. Test: can you describe the module's job without using the word "and"? Mixing import-parsing + scoring + persistence in one function violates SoC; split into three functions. See `AI-CODING-GUIDELINES.md` § Design principles | Separation of Concerns / SoC |
| a design principle that says validate inputs at the boundary and raise immediately on invariant violations. Don't paper over with silent defaults that hide the bug. A `ValueError("weight must be ≥ 0")` at function entry is far easier to debug than a wrong answer five layers deep. See `AI-CODING-GUIDELINES.md` § Design principles | Fail Fast |
| "Keep It Stupidly Simple" — pick the simplest design that solves the real problem. Three similar lines is better than a premature abstraction. Don't design for hypothetical future requirements. Pairs with DRY; they argue with each other on purpose | KISS |
| "Don't Repeat Yourself" — when the same logic appears 3+ times AND is genuinely re-usable, extract a named helper. Two occurrences usually aren't enough; the third occurrence proves the pattern. Pairs with KISS | DRY |
| the failure mode where you abstract code that doesn't justify abstraction — an abstraction with one caller, where the duplicated code is shorter than the abstraction's signature, or where the justification is "I might need this elsewhere later". The cure is to leave the duplication and revisit when a real third caller appears. See `AI-CODING-GUIDELINES.md` § KISS and DRY | over-DRY trap |
| a commit that does one thing, with a title under 70 chars, a body explaining the WHY (not the WHAT), and a reference to any tracked issue ID. Forbidden generic titles: `fix`, `update`, `wip`, `stuff`, `misc`. See `AI-CODING-GUIDELINES.md` § Commit-message rules | atomic and descriptive commit |
| the explicit human-approval gate required before any code is written for a change that touches core architecture, database schema (data migration), global state, public API contract, security model, or ABSOLUTE-rule-adjacent territory. Format: `[REVIEW GATE: awaiting approval]` after a 3-5 bullet summary. Cannot be bypassed by auto mode or session prompt. See `AI-CODING-GUIDELINES.md` § Major-change review gates | review gate / REVIEW GATE marker |
| a stable Ubuntu release that Canonical supports for 5 years and receives security patches for 10 years (e.g., 20.04 LTS, 22.04 LTS); the GitHub Actions `ubuntu-latest` runner ships the current LTS version | LTS / Long-Term Support |
| a compiler flag that enables Mull mutation testing — wires the Mull LLVM plugin into the Clang compilation pipeline so code mutations can be injected at the IR level; e.g. `-fpass-plugin=mull-ir-frontend` | -DMULL / DMULL / Mull flag |

| the required opening marker that says the agent knows its own code must pass the coding rules, required tests, coverage target, mutation tests, and local check setup before commit | QUALITY GATE READ marker |
| the required handoff marker for code-changing sessions; it records that guidelines, tests, coverage, mutation tests, and check setup all passed before commit | QUALITY GATE RESULT marker |
| the quality-result field that says the required local tools, commands, containers, and test setup all ran correctly | check_setup |

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
