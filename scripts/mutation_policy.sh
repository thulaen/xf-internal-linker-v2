#!/usr/bin/env bash

mutation_parse_args() {
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --mutation-mode)
        if [[ "$#" -lt 2 ]]; then
          echo "mutation policy: --mutation-mode needs scoped or full" >&2
          exit 2
        fi
        MUTATION_MODE="$2"
        shift 2
        ;;
      --mutation-mode=*)
        MUTATION_MODE="${1#*=}"
        shift
        ;;
      --full-mutation|--mutation-full)
        MUTATION_MODE="full"
        shift
        ;;
      --scoped-mutation|--mutation-scoped)
        MUTATION_MODE="scoped"
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  MUTATION_MODE="${MUTATION_MODE:-scoped}"
  if [[ "$MUTATION_MODE" != "scoped" && "$MUTATION_MODE" != "full" ]]; then
    echo "mutation policy: MUTATION_MODE must be scoped or full, got '$MUTATION_MODE'" >&2
    exit 2
  fi
  export MUTATION_MODE
}

mutation_refuse_full_in_hook() {
  if [[ "$MUTATION_MODE" == "full" && "${PRE_COMMIT:-0}" == "1" ]]; then
    echo "mutation policy: full mutation is not allowed inside the precommit hook" >&2
    exit 2
  fi
}

mutation_diff_file() {
  if [[ -n "${MUTATION_DIFF_FILE:-}" && -f "$MUTATION_DIFF_FILE" ]]; then
    export MUTATION_DIFF_FILE
    return 0
  fi

  MUTATION_DIFF_FILE="${TMPDIR:-/tmp}/xf-rust-mutation.diff"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git diff --cached -- services rust > "$MUTATION_DIFF_FILE" || true
    if [[ ! -s "$MUTATION_DIFF_FILE" ]]; then
      git diff -- services rust > "$MUTATION_DIFF_FILE" || true
    fi
  else
    : > "$MUTATION_DIFF_FILE"
  fi
  export MUTATION_DIFF_FILE
}

mutation_log() {
  local tool="${1:-unknown}"
  local target="${2:-unknown}"
  local jobs="${3:-unknown}"
  echo "[mutation] tool=$tool target=$target jobs=$jobs mode=${MUTATION_MODE:-scoped}"
}
