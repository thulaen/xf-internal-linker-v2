# Agent Handoff Log

**All agents (Claude, Codex, Gemini) must:**
- Read the most recent entry here at session start, before any other work.
- Append a new entry at session end (or when stopping mid-task).

Be specific — the next agent has no memory of your session. Explain the *why*, not just the *what*.

---

## TEMPLATE (copy this for each new entry)

```
## [YYYY-MM-DD] Agent: [Claude | Codex | Gemini]

### What I did
- [concrete task, file changed, PR merged, etc.]

### Key decisions and WHY
- [e.g. "Chose Option B over Option A because Option A broke the benchmark — see bench_scorer.cpp"]

### What I tried that didn't work
- [so the next agent doesn't repeat dead ends]

### What I explicitly ruled out
- [e.g. "Do not re-add the dev Angular server — see docs/DELETED-FEATURES.md"]

### Context the next agent must know
- [anything non-obvious about the current state of the code]

### Pending / next steps
- [ ] ...

### Open questions / blockers
- ...
```

---

## 2026-04-23 Agent: Claude

### What I did
- Created this file (`AGENT-HANDOFF.md`) as the shared inter-agent coordination layer.
- Added handoff read/write rules to `CLAUDE.md` and `AGENTS.md` so all three agents (Claude, Codex, Gemini) pick them up automatically at session start.
- Removed stale `[extensions] worktreeConfig = true` from `.git/config` — this was left behind by a Claude Code worktree operation and was causing Gemini to silently refuse to respond.

### Key decisions and WHY
- File-based handoff chosen over an MCP server: no infrastructure to run, works offline, version-controlled, and fits the existing document-based coordination pattern already in place (AI-CONTEXT.md, AGENTS.md, REPORT-REGISTRY.md).
- Rules added to both `CLAUDE.md` (Claude-specific) and `AGENTS.md` (Codex + Gemini) so all agents see them regardless of which file they read.

### What I tried that didn't work
- N/A (setup session, no dead ends)

### What I explicitly ruled out
- MCP server approach: adds a running process dependency; overkill for read-at-start / write-at-end coordination.

### Context the next agent must know
- Gemini reads `AGENTS.md` (no `GEMINI.md` exists in this repo — confirmed 2026-04-23). If you create a `GEMINI.md` in future, add the handoff rule there too.
- The `worktreeConfig` extension gets re-added automatically if Claude Code runs an agent with `isolation: "worktree"`. If Gemini stops responding again, check `.git/config` for that block.

### Pending / next steps
- [ ] No active tasks. Check `AI-CONTEXT.md` for the current project queue.

### Open questions / blockers
- None.
