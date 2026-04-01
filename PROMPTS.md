# PROMPTS.md

Workflow guidance for AI tools working in this repo.

## Global Rules

Before coding in any new session:

1. Read `AI-CONTEXT.md`.
2. Read `FEATURE-REQUESTS.md`.
3. Read this file.
4. Inspect the repository and reconcile docs against code before trusting status text.

Project rules:
- FR IDs are permanent request IDs; phase numbers are execution order.
- Implement exactly one active delivery phase per session unless the repo already proves that phase is complete.
- GUI-first after setup.
- Django + DRF backend, Angular frontend.
- PostgreSQL + pgvector for persistence.
- Redis for cache, broker, and channels.
- Celery for background work; no inline heavy processing.
- WebSockets for real-time updates; no HTTP polling.
- Read-only access to XenForo and WordPress APIs.
- Update `AI-CONTEXT.md` and `FEATURE-REQUESTS.md` before stopping.
- Update this file only when workflow guidance has drifted.
- For future ranking-affecting features, treat C++ as the default execution path for the hot loop, keep a behavior-matching Python fallback, and add a plain-English reason field or diagnostic on the dashboard or diagnostics UI when the C++ speed path is missing, skipped, falling back, or not helping enough.

User communication rules:
- Assume the user prefers layman's terms unless they ask for a deep technical explanation.
- Default to: "AI should talk to me in plain English and explain things like I'm five."
- Start explanations with the plain-English version of what happened and why it matters.
- Explain the simple version first, using short sentences, concrete examples, and everyday words.
- Minimize jargon; when jargon is necessary, define it immediately in simple language.
- When reporting verification, make the real-world meaning explicit, for example whether the app works, what is still broken, and what the next step is.

Git rules:
- Start every session with `git status --short`.
- Treat a dirty worktree as shared state.
- Prefer ending each safe session with a clean worktree after a narrow commit and push.
- If you cannot leave the tree clean, add a short handoff note to `AI-CONTEXT.md` that names the AI/tool, the files changed, commit status, and what remains dirty.
- Pull only when appropriate and safe.
- At session end, stage only intended files.
- Never stage `tmp/`, `backend/scripts/`, or unrelated changes.
- Never use `git add -A` in a dirty tree.
- Commit with a descriptive message when the slice is verified as far as the environment allows.
- Push automatically only when safe.

## Tool Guidance

- Codex: implementation, backend wiring, frontend wiring, tests, bug fixes.
- Claude Code: architecture review, risk validation, skeptical review before broad refactors or phase-complete claims.
- Gemini or other frontend-focused tools: Angular/Material UX work only after backend contracts are stable.

Image verification (use after any docker-compose build):

    docker images | grep xf-linker

Expected output: one or more rows whose REPOSITORY column contains `xf-linker`. If the
command returns nothing, the build did not produce the expected images and the session must
not proceed to commit.

## Decision-First Prompt

```text
Read AI-CONTEXT.md and FEATURE-REQUESTS.md, inspect the repo, and reconcile docs against code.

Then report:
1. current phase and FR cross-reference
2. whether the repo is on-plan, ahead, behind, or drifting
3. the best tool for the next task
4. 2 to 4 sensible next-task options
5. one recommended option
6. the exact files you expect to touch

Do not start coding until I confirm, unless I explicitly say to proceed.
```

## One-Slice Implementation Prompt

```text
Read AI-CONTEXT.md and FEATURE-REQUESTS.md first, then inspect the repo.

Before coding, run `git status --short` and say whether the worktree is clean or dirty.
If dirty, name the files you expect to touch and confirm you will not sweep unrelated changes into your commit.

Implement exactly one active phase only.

Before coding:
- restate the active phase and FR ID
- state whether the docs match the repo
- list the exact files you expect to touch
- state what is out of scope

During implementation:
- preserve architecture and guardrails
- keep the slice narrow
- heavy work belongs in Celery tasks, not request handlers
- add tests for new functionality
- if the slice affects ranking or reranking, make the hot loop use C++ as the default execution path when practical, preserve the Python fallback, and include dashboard or diagnostics UI output that explains whether the fast path is active, whether fallback is being used, and why it is not materially faster when that happens

At the end:
- summarize what changed
- summarize verification
- name the next exact phase and FR ID
- update AI-CONTEXT.md in a single pass: first record the phase completion (phase ledger
  entry, next phase pointer, What Changed summary); then, if the worktree is still dirty,
  append a Current Session Note that names the AI/tool, the exact files intentionally changed,
  commit status, and what remains uncommitted and why — both updates belong in one write
- update FEATURE-REQUESTS.md
- if workflow guidance drifted, update PROMPTS.md too
- if Git is safe, stage intended files, commit, and push
```

## Universal Resume Prompt

```text
Read AI-CONTEXT.md and FEATURE-REQUESTS.md first, inspect the repo, and resume from the latest completed phase.

Run `git status --short` before planning and report whether the worktree is clean or dirty.

Then report:
1. current phase and FR cross-reference
2. whether the repo is on-plan, ahead, behind, or drifting
3. what appears complete in code
4. the next exact phase
5. expected files to touch
6. blockers or risks

Then continue with one phase only.
```

## Session Close-Out Prompt

```text
Before ending the session:
1. update AI-CONTEXT.md in a single pass: record phase completion (phase ledger, next phase
   pointer, What Changed summary); if the worktree is still dirty, append a Current Session
   Note naming the AI/tool, exact files changed, commit status, and what remains uncommitted
   and why — one write, not two
2. update FEATURE-REQUESTS.md
3. update PROMPTS.md only if workflow guidance drifted
4. summarize exactly what changed
5. summarize verification performed
6. name the next exact phase and FR ID
7. if Git is safe, stage intended files, commit, and push
8. if Git is not safe, explain why
```
