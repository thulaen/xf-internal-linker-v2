# run-agent-progress.ps1
#
# Invoked by the "XFLinker - Agent Progress" Scheduled Task every 10 minutes.
# It refreshes audit/agent_progress_latest.txt (the shared cross-agent progress
# line) and pops a Windows desktop alert if a quality/mutation container has
# stalled (the 0%-CPU wedge) or a mutation lock has been held too long.
#
# This is the agent-INDEPENDENT pulse: it keeps the status fresh and visible
# even when no agent (Claude / Codex / Gemini / Antigravity) is replying.
# Best-effort by design — it must never throw or pop an error.

$ErrorActionPreference = 'SilentlyContinue'

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $py) { exit 0 }   # no python on this task's PATH — nothing to do

& $py "scripts/agent_progress.py" --background --notify-on-stuck --label "background watch" | Out-Null
exit 0
