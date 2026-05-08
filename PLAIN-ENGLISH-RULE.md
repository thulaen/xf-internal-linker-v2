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
