# GLOSSARY-RULE.md — Update the Plain-English Glossary in the Same Change

**Status:** PARAMOUNT for any change that introduces a new technical thing — a feature, a signal, a setting, an acronym (FR-XXX / RPT-XXX / ISS-XXX / MMR / FAISS / RSQVA / etc.), a framework name, an abbreviation, or any vocabulary that the user would not understand on first read.

## The Rule

If you introduce a new technical word, you must add a one-line plain-English entry for it to the glossary table in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md) **in the same commit**. Not a follow-up commit. Not "I'll do it later". The same commit.

The pre-commit hook [`.githooks/check-glossary.py`](.githooks/check-glossary.py) enforces this. Commits that introduce a new acronym without a matching glossary entry are blocked with a clear error message that names the acronym, the file it appeared in, and how to fix it.

## What counts as "a new technical thing"

- **Acronyms / abbreviations**: any 3+ consecutive uppercase letters not already in the table or the allowlist. Examples: `MCP`, `BGE-M3`, `FAISS`, `MMR`, `RSQVA`, `HGTE`, `HITS`, `PPR`.
- **Project shorthand**: anything matching `FR-\d{3}`, `RPT-\d{3}`, `ISS-\d{3}`. Each numbered identifier needs an entry the first time it appears in committed text outside the report registry.
- **Framework / tool names** that the user might not recognise: `Ollama`, `Daphne`, `pgvector`, `croniter`, etc.
- **Domain jargon**: words like `embedding`, `reranking`, `hyperparameter`, `cyclomatic complexity`. The existing table already covers many — extend the table when a new one slips in.

## What does NOT count

The hook ships with an explicit allowlist of common false-positives that don't need glossary entries:

```
CSS, HTML, URL, API, JSON, HTTP, HTTPS, CSV, JSX, TSX, SCSS, DRF, ORM, SQL,
DOM, AST, GUI, CLI, UI, UX, ID, IDs, SDK, REST, RPC, JWT, TLS, SSL, CRC, MD5,
SHA, UUID, ISO, RFC, GMT, UTC, OS, CPU, GPU, RAM, ROM, USB, IP, IPv4, IPv6,
TCP, UDP, MIME, PNG, JPG, JPEG, GIF, SVG, PDF, MP3, MP4, ZIP, TAR, GZ
```

Common framework names that have an existing glossary entry are also exempt (e.g. `Django`, `Angular`, `Docker`, `Redis`).

## How to add an entry

Open [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md). Find the markdown table under the "Jargon Glossary" section. Add a row:

```markdown
| <plain-English substitute, lowercase, conversational> | <technical jargon to avoid (or always define)> |
```

Example for a new term `MCP`:

```markdown
| the standard way modern AI agents call external tools | MCP / Model Context Protocol |
```

Tone: conversational. Use everyday metaphors. Define what it DOES, not what it IS technically.

## Examples — right and wrong

### Right

A commit that adds `croniter` (a Python library for parsing cron schedule expressions) to `backend/requirements.txt` AND adds a row to the glossary table:

```markdown
| a Python library that knows how to read cron schedule expressions like "every Monday at 9am" | croniter |
```

The pre-commit hook sees `croniter` in the diff, finds the matching row in the table, and lets the commit through.

### Wrong

A commit that adds `croniter` to `backend/requirements.txt` without touching the glossary. The hook fails with:

```
✗ check-glossary: 1 new term used without a plain-English glossary entry.

  croniter — appeared in backend/requirements.txt:42

To fix: add a row to PLAIN-ENGLISH-RULE.md describing the term in plain English.
If the term is genuinely a false-positive, add it to the allowlist in
.githooks/check-glossary.py.
```

## Forbidden patterns

- ❌ Introducing a new acronym in chat output without defining it in the same sentence.
- ❌ Adding a new term to a comment / docstring / CLAUDE.md PARAMOUNT line / handoff entry without a glossary entry.
- ❌ Bypassing the hook with `--no-verify` (forbidden by `CLAUDE.md` and `AGENTS.md` already).
- ❌ Silently adding the term to the allowlist instead of the glossary.

## Why this rule exists

The user is a vibe coder. They don't write code, and they read the project's chat output, commit messages, handoffs, and reports. Every undefined acronym is a small barrier between them and understanding their own app. The glossary is the project's single shared dictionary — when it stays current, every other surface is easier to read. When it falls behind, every chat message needs the user to ask "what does that mean?" again. This rule keeps the dictionary in step with the code.
