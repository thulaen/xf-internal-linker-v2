# MCP setup — connect your AI agent to the linker

This file explains in plain English how the AI Agents page works, what gets
wired up automatically, and what to do when something doesn't behave.

## What MCP is

MCP — short for **Model Context Protocol** — is the standard way modern AI
coding agents (Claude Code, Codex, Antigravity) call external tools. Once
the linker app exposes an MCP server, your AI agent can ask the app to
"list orphan content" or "give me top-300 candidate suggestions" without
you copy-pasting anything.

## How it auto-wires

The repo ships a project-scope config file at the root: `.mcp.json`. The
first time you open this project folder in Claude Code, Claude Code
auto-discovers that file and shows a one-line approval dialog ("Allow
project MCP servers?"). Click **Approve** once. From then on, every
session opened in this folder has the `xf-internal-linker` MCP server
available — no `claude mcp add`, no manual config edits.

The MCP server itself runs inside the existing backend Docker container.
There's no separate process to start; Claude Code launches the server
on demand via `python scripts/backend_manage.py`.

## What the AI agent can call

The MCP server exposes three read-only tools in v1:

| Tool | What it does |
|------|--------------|
| `get_top_candidates(month, n=300)` | Pull the top-N pending link suggestions ordered by composite score. |
| `get_dashboard_metrics()` | One-shot snapshot of suggestion-status counts. |
| `list_orphans(limit=25)` | Articles with no approved or applied incoming links. |

More tools are planned (`suggest_links`, `find_semantic_pairs`,
`gap_analysis`, `search_content`, `get_review_queue`) and ship
incrementally. Adding a tool is a one-function change at the bottom of
`backend/mcp_server.py`.

## Per-agent status — current

- **Claude Code** — full support via project-scope `.mcp.json`. Click
  Approve once on first session; works forever after.
- **Codex CLI** — best-effort. Codex's MCP support is still evolving;
  the same `.mcp.json` schema usually works but is not guaranteed.
- **Antigravity** — not supported yet. Antigravity has not shipped an
  MCP server. The AI Agents page row says so explicitly. When
  Antigravity adds MCP, supporting it is one extra branch in the
  detection logic.

## Sentient schedules — auto-recovery of missed runs

The app's schedule tracker watches every registered scheduled task. If
your laptop is off when a schedule fires, the tracker notices the missing
slot the moment Django boots and runs the missed job — with a 5-30 second
random delay (jitter) so multiple missed jobs don't fire at the exact
same second.

You can see every registered schedule on the **AI Agents** page under the
**Schedules** card: task name, cron expression, next run, last run, and a
chip showing the last status. The "(recovered)" suffix on a status chip
means that run was fired by the catch-up sweep rather than the normal
cron. A "Run now" button per row lets you fire any schedule on demand.

## Monthly Top-50 — the headline use case

On the 1st of every month at 09:00 UTC, the app runs a **monthly Top-50**
job that picks the 50 strongest internal-link suggestions and writes them
as a markdown report at `docs/reports/monthly-suggestions-YYYY-MM.md`.

There are two strategies:

- **Strategy A (Claude Code)** — preferred when Max 5x is active. The
  AI applies the editorial rules (max 3 per source thread, max 2
  anchors, score floor 0.70, freshness bias) and writes the report.
- **Strategy B (pure Python)** — the always-on fallback. Same editorial
  rules, deterministic, no LLM. The picks come from the existing
  composite-score ranking. Per-pick "why this is a good pick" is built
  from the score breakdown.

The router in `backend/apps/pipeline/services/strategy_router.py` pings
`claude -p ping` with a 5-second timeout. If it answers, Strategy A is
used; otherwise Strategy B. You can pin to Strategy B with the
`MONTHLY_STRATEGY=python` environment variable.

## What you do, ongoing

Open the app in your browser. Click **AI Agents** in the sidenav for live
status + schedules. Click **Monthly Reports** to read the latest pick list.
That's it.

Never a terminal. Never a copy-paste of MCP setup commands. The only
non-browser thing you'll ever do is click "Approve" the very first time
Claude Code asks about the project's `.mcp.json` — that's a Claude Code
dialog, not a command line.

## Troubleshooting

**The AI Agents page says "Not ready".** Check the three signal flags
in the MCP server status card. If `Python mcp package` shows "not
installed", rebuild the backend container so it picks up the new
`mcp` dependency in `requirements.txt`.

**Claude Code doesn't see the MCP server.** Confirm `.mcp.json` is at
the repo root and you opened Claude Code from inside this folder.
Check Claude Code's `/mcp` command for the connection state.

**A scheduled run looks stuck on "running" forever.** The tracker
records `pending` → `running` → `succeeded`/`failed`. If something
crashes between `running` and a terminal status, the row stays
`running` until manual intervention. Use the "Run now" button to
re-fire the schedule — the tracker's unique constraint will update
the existing row rather than create a duplicate.

**My monthly report didn't generate when expected.** Check the
Schedules card — the next run is shown there. If you were offline
when the schedule fired, the recovery sweep on next boot picks it
up automatically; you don't have to do anything. To force a run
right now, click "Run monthly Top-50 now".
