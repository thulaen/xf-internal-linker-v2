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
