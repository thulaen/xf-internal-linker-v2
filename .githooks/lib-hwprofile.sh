#!/bin/bash
# lib-hwprofile.sh — sourced by .githooks/pre-commit and .githooks/pre-push.
#
# Exports MAX_JOBS_FAST and MAX_JOBS_HEAVY based on the detected hardware
# tier (see backend/apps/pipeline/services/hardware_profile.py). Honours
# caller-set values so devs can pin their own caps via shell env.
#
# Fallback when the Python module isn't reachable (e.g. fresh checkout
# before pip install): a conservative laptop tier (FAST=2, HEAVY=2).
# That keeps pre-commit / pre-push functional on day-0 without forcing a
# slow backend round-trip into every commit.
#
# Why a shell helper and not a Python script: pre-commit must stay fast
# on every commit. Sourcing a shell file is ~1 ms; spawning a Python
# interpreter is ~100 ms. The Python interpreter only fires when the
# fast-band step actually needs the caps.

# If the caller already set both env vars, respect them and exit early.
if [ -n "${MAX_JOBS_FAST:-}" ] && [ -n "${MAX_JOBS_HEAVY:-}" ]; then
  return 0 2>/dev/null || exit 0
fi

_hwprofile_json=""
_repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"

# Try local Python first (fastest path — works when backend deps are pip-installed locally).
if command -v python > /dev/null 2>&1; then
  _hwprofile_json=$(cd "$_repo_root/backend" 2>/dev/null && python -m apps.pipeline.services.hardware_profile --json 2>/dev/null || echo "")
fi

if [ -n "$_hwprofile_json" ] && command -v python > /dev/null 2>&1; then
  _fast=$(echo "$_hwprofile_json" | python -c "import json,sys; print(json.load(sys.stdin).get('max_jobs_fast', 2))" 2>/dev/null || echo "2")
  _heavy=$(echo "$_hwprofile_json" | python -c "import json,sys; print(json.load(sys.stdin).get('max_jobs_heavy', 2))" 2>/dev/null || echo "2")
else
  # Conservative laptop defaults — keep heavy band at 2 so a fresh checkout
  # never crashes the machine on first pre-commit.
  _fast="2"
  _heavy="2"
fi

export MAX_JOBS_FAST="$_fast"
export MAX_JOBS_HEAVY="$_heavy"
