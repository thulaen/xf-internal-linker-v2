#!/usr/bin/env bash
# Phase J: thin wrapper around the GitHub CLI (`gh`).
#
# Per the user policy (2026-05-18):
#   - Agents use `gh` to find the latest pushed commit only.
#   - If `gh` is not installed / not authenticated / fails, the agent
#     files an AutoIssue tracking the broken tooling so the next
#     session resolves it.
#   - The session that filed the AutoIssue STILL completes its 30-pick
#     quota; it just falls back to local `git` for the pushed-commit
#     lookup.
#
# Source this file from any script that needs `gh`:
#
#   . scripts/_gh_helper.sh
#   latest_sha="$(gh_latest_pushed_commit_or_autoissue origin master)"
#   if [ -z "$latest_sha" ]; then
#     # gh failed; use local fallback. The AutoIssue was already filed.
#     latest_sha="$(git rev-parse origin/master 2>/dev/null || echo unknown)"
#   fi
#
# The helper never `exit`s the caller. It returns empty on failure
# and writes a Rule-F warning + files an AutoIssue.

set -u

# Where to record gh failures so the next session sees them.
# Path is repo-relative; the caller must be in repo root for the
# AutoIssue write to find Django (via docker compose exec).
GH_HELPER_AUTOISSUE_CATEGORY="${GH_HELPER_AUTOISSUE_CATEGORY:-gh_tooling_broken}"

# K8: differentiate "missing" (gh not on PATH) from "auth_expired"
# (gh installed but `gh auth status` non-zero). Each returns a
# distinct return code so the caller can file the right AutoIssue.
#
# Returns:
#   0  - gh available + authenticated
#   1  - gh not on PATH (missing)
#   2  - gh on PATH but auth not configured (auth_expired)
gh_status() {
  if ! command -v gh >/dev/null 2>&1; then
    return 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    return 2
  fi
  return 0
}

# Backwards-compat alias for callers that only need a boolean.
gh_available() {
  gh_status
  [ "$?" -eq 0 ]
}

# gh_latest_pushed_commit_or_autoissue <remote> <branch>
# Returns the SHA on stdout when gh works. On failure, prints a
# warning + files an AutoIssue (with the RIGHT kind per K8) and
# returns 1 with empty stdout.
gh_latest_pushed_commit_or_autoissue() {
  local remote="${1:-origin}"
  local branch="${2:-master}"
  local rc
  gh_status
  rc=$?
  if [ "$rc" -eq 1 ]; then
    _gh_helper_file_autoissue missing \
      "scripts/_gh_helper.sh tried to read latest pushed commit on $remote/$branch but gh is not on PATH"
    return 1
  fi
  if [ "$rc" -eq 2 ]; then
    _gh_helper_file_autoissue auth_expired \
      "scripts/_gh_helper.sh tried to read latest pushed commit on $remote/$branch but gh auth status returned non-zero"
    return 1
  fi
  # gh api endpoint: /repos/{owner}/{repo}/branches/{branch}
  local sha
  sha="$(gh api "repos/{owner}/{repo}/branches/$branch" --jq '.commit.sha' 2>/dev/null || true)"
  if [ -z "$sha" ]; then
    _gh_helper_file_autoissue api_failure \
      "gh api repos/{owner}/{repo}/branches/$branch returned empty"
    return 1
  fi
  echo "$sha"
  return 0
}

# Internal: file an AutoIssue tracking a gh tooling failure.
# K6: uses argv (not a heredoc with shell interpolation) so any
# value can contain apostrophes / quotes / backslashes without
# breaking the embedded Python.
# K8: takes a `kind` argument (missing / auth_expired / api_failure)
# so each kind gets its own AutoIssue row.
#
# Usage:  _gh_helper_file_autoissue <kind> <context>
_gh_helper_file_autoissue() {
  local kind="$1"
  local context="$2"
  # Emit a Rule-F warning regardless of whether the AutoIssue can be
  # filed, so the operator sees the failure.
  cat >&2 <<EOF
WARN _gh_helper: gh CLI failure kind=$kind
WHY: $context
UNBLOCK: see the AutoIssue's lessons_learned for the per-kind fix path
NOTE: AutoIssue will be filed (category=$GH_HELPER_AUTOISSUE_CATEGORY, kind=$kind) so the next session resolves the tooling gap. Caller is expected to fall back to local git for now.
EOF
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  if ! docker compose ps backend --format json 2>/dev/null | grep -q '"State":"running"'; then
    # Backend not running — can't file via Django. Silent.
    return 0
  fi
  # K6: argv form — no shell interpolation into Python source. The
  # Django command at file_gh_helper_autoissue.py validates --kind.
  docker compose exec -T backend python manage.py file_gh_helper_autoissue \
    --kind "$kind" \
    --context "$context" \
    --agent claude >/dev/null 2>&1 || true
  return 0
}
