#!/usr/bin/env bash

xf_findings_transcript_path() {
  if [[ -n "${XF_FINDINGS_TRANSCRIPT:-}" ]]; then
    printf "%s\n" "$XF_FINDINGS_TRANSCRIPT"
    return 0
  fi

  local message_path
  message_path="$(git rev-parse --git-path COMMIT_EDITMSG 2>/dev/null || true)"
  if [[ -z "$message_path" ]]; then
    message_path="COMMIT_EDITMSG"
  fi

  local attempt_id
  attempt_id="$(printf "%s" "$message_path" | sed -E 's/[^A-Za-z0-9_.-]+/_/g')"
  if [[ -z "$attempt_id" ]]; then
    attempt_id="commit"
  fi

  printf "%s/xf-findings-%s.txt\n" "${TMPDIR:-/tmp}" "$attempt_id"
}
