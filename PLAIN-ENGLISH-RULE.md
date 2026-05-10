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

**Before sending ANY response, answer YES to all four questions. If any answer is NO, rewrite the response first.**

1. **Terms defined?** Is every technical term defined in plain English in the same sentence where it first appears?
2. **Grandmother test?** Would someone who has never written code understand every sentence without needing to look anything up?
3. **Three parts covered?** Have I stated what I'm doing, what was accomplished, and what (if anything) has issues?
4. **No bare acronyms?** Have I avoided all unexplained acronyms — FR-XXX, ISS-XXX, MMR, BGE-M3, FAISS, RSQVA, and any other project shorthand?

**If ANY answer is NO → rewrite before sending.**

---

## Jargon Glossary — Use These Substitutes

When you must mention a technical concept, use the plain-English version from the left column. Never use the right column without defining it first.

| Plain-English substitute | Technical jargon to avoid (or always define) |
|--------------------------|-----------------------------------------------|
| number-fingerprints that capture meaning | embeddings |
| our similarity search engine that finds alike content | FAISS |
| a database update script | migration |
| a scoring factor | signal |
| re-sorting results using better criteria | reranking |
| a setting that controls how the AI behaves | hyperparameter |
| code that runs thousands of times per second | hot path |
| a speed-boosted module written in a faster language (C++) | C++ extension |
| the background task runner | celery worker |
| the framework that builds the visual interface | Angular |
| the framework that handles data storage and business logic | Django |
| a packaging system that makes the app run the same everywhere | Docker |
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
| a tag we put on a link suggestion to mark it as picked but not yet applied | proposed |
| Windows' built-in tool that runs a script at a specific time and date | Windows Task Scheduler |
| a way an AI agent talks to a tool by exchanging text on standard input/output | stdio |
| a way for a server to push updates to a browser as soon as they happen | HTTP-SSE / Server-Sent Events |
| a small program that lets you run AI language models on your own laptop | Ollama |
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
| the project's session-start rule that every AI agent must fix three open issues from the auto-issues table before working on whatever the user asked for — raised from two on 2026-05-09 to keep the open queue from growing faster than agents close it | auto-fix-3 / auto-fix-3 satisfier / fix three before any new task |
| the marker line every AI agent puts in its first response proving it read the open auto-issues + Report Registry — looks like `[REGISTRY READ: 5 open auto-issues, 12 open registry findings — picked: #ISS-101, #ISS-102, #ISS-103]`; required by the ABSOLUTE rule in CLAUDE.md / AGENTS.md / CODEX.md / GEMINI.md | REGISTRY READ marker |
| the second-line marker an AI agent posts after running `search_resolved_issues` for a touched code area — looks like `[RESOLVED HISTORY: 3 prior fix(es) read in backend/apps/audit]`; proves the agent read prior `lessons_learned` so it doesn't repeat known traps | RESOLVED HISTORY marker |
| a `Path: <repo-relative-path>` argument the agent passes to `manage.py search_resolved_issues` — surfaces the trap + fix-shape from every prior fix in that directory so the next session doesn't repeat the mistake | search_resolved_issues |
| the registry of every per-content database table that follows the `(content_hash, signal_version) skip-if-unchanged + supersede + retention` pattern — defined in NO-DUPLICATES.md, audited at boot via `apps.core.services.self_test_smoke.run_startup_smoke_tests`, gated in CI by `scripts/verify_dedup_invariant.py` | NO-DUPLICATES invariant / no-dups invariant |
| the canonical Python registry that lists every weight + meta-algorithm parameter the autotuner is allowed to adjust — at `backend/apps/suggestions/tunable_registry.py`; new keys MUST land here in the same commit they're introduced (per `docs/AUTOTUNER-FUTURE-AWARENESS.md`) | tunable_registry / BLEND_WEIGHTS / META_PARAMS |
| the file every AI agent must read before any task — consolidates the "fix as you go" + "report severe to BOTH AutoIssue + Registry" rules + the auto-fix-3 count in one place; replaces what used to be inline blocks scattered across CLAUDE.md / AGENTS.md / CODEX.md / GEMINI.md | ONGOING-CODE-QUALITY.md |
| a small Python module at `backend/apps/pipeline/services/disk_pressure.py` that pre-flights large file writes against free-disk watermarks (GREEN/YELLOW/RED/CRITICAL) and raises `DiskPressureError` when the projected write would push free disk below the safety margin; refreshed every 60 s by a Celery beat task | disk_pressure / DiskPressureError / require_free_disk |
| Video memory — the dedicated RAM that lives on the graphics card; used to hold model weights and embedding tensors during GPU computation; separate from main system RAM | VRAM |
| Industry-standard tracing/metrics framework used to record what every backend request and Celery task does, where time is spent, and whether errors happened; the project sends OpenTelemetry data to GlitchTip's Performance tab | OpenTelemetry / OTEL |
| Foreign Function Interface — the boundary where Python calls into C++ (via pybind11) or vice-versa; used in the project's hot-path rerankers so the slow Python ranking math is replaced by fast C++ kernels | FFI |
| Near-Real-Time — describes scoring or retrieval that happens within seconds of an event (vs. batch jobs that run nightly); the project's NRT signals power live confidence-meter updates and the autotuner's short-window feedback loop | NRT |
| pre-commit hook script at `.githooks/check-file-size.py` that blocks commits adding a file over 1,500 lines (the cap from CLAUDE.md), and prevents grandfathered files (listed in `.githooks/file-size-grandfather.txt`) from growing past their recorded baseline | check-file-size / file-size-grandfather |
| pre-commit hook script at `.githooks/check-no-downgraded-gates.py` that blocks any commit which silently flips a CI gate from blocking to warning-only (`\|\| true`, `continue-on-error: true`, `exit-code: '0'`, `::warning::`) unless the same diff also adds a `# GATE-DOWNGRADE-JUSTIFICATION:` comment with a real reason | check-no-downgraded-gates / GATE-DOWNGRADE-JUSTIFICATION |
| pre-commit hook script at `.githooks/check-frontend-routes.py` that scans every `HttpClient.get/post/put/patch/delete('/api/...')` call in staged frontend TypeScript files and verifies the URL resolves to a real `path('...')` declaration in `backend/apps/**/urls.py`; prevents stale frontend → backend URL drift | check-frontend-routes |
| pre-commit hook script at `.githooks/check-missing-tests.py` that blocks commits which add a new `*.component.ts`, `*.service.ts`, or `backend/apps/*/services/*.py` file without a matching test file (sibling `.spec.ts` for frontend, `test_<base>.py` in same/parent/tests dir for backend) | check-missing-tests |

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
