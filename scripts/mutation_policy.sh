#!/usr/bin/env bash
# Shared mutation wrapper policy: incremental by default, full only on request.

MUTATION_MODE="${MUTATION_MODE:-incremental}"
MUTATION_DIFF_REF="${MUTATION_DIFF_REF:-origin/main}"
MUTATION_SUBSYSTEM="${MUTATION_SUBSYSTEM:-all}"
MUTATION_WORKERS="${MUTATION_WORKERS:-}"
MUTATION_SCHEMATA="${MUTATION_SCHEMATA:-on}"
MUTATION_COVERAGE="${MUTATION_COVERAGE:-on}"
MUTATION_DIFF_FILE="${MUTATION_DIFF_FILE:-}"

mutation_parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --full)
        MUTATION_MODE="full"
        ;;
      --diff-ref)
        shift
        MUTATION_DIFF_REF="${1:-origin/main}"
        ;;
      --subsystem)
        shift
        MUTATION_SUBSYSTEM="${1:-all}"
        ;;
      --workers)
        shift
        MUTATION_WORKERS="${1:-}"
        if [ -n "$MUTATION_WORKERS" ]; then
          export XF_QUALITY_CORES="$MUTATION_WORKERS"
        fi
        ;;
      --use-schemata)
        MUTATION_SCHEMATA="on"
        ;;
      --no-schemata)
        MUTATION_SCHEMATA="off"
        ;;
      --use-coverage)
        MUTATION_COVERAGE="on"
        ;;
      --no-coverage)
        MUTATION_COVERAGE="off"
        ;;
      --clean)
        export MUTATION_CLEAN=1
        ;;
      *)
        echo "Unknown mutation wrapper argument: $1" >&2
        return 2
        ;;
    esac
    shift
  done
  if [ "${XF_MUTATION_FULL:-0}" = "1" ]; then
    MUTATION_MODE="full"
  fi
  export MUTATION_MODE MUTATION_DIFF_REF MUTATION_SUBSYSTEM
  export MUTATION_WORKERS MUTATION_SCHEMATA MUTATION_COVERAGE
}

mutation_refuse_full_in_hook() {
  if [ "$MUTATION_MODE" != "full" ]; then
    return 0
  fi
  if [ -n "${GIT_HOOK_NAME:-}" ] || [ -n "${XF_HOOK_CONTEXT:-}" ] || [ -n "${PRE_COMMIT:-}" ] || [ -n "${PRE_PUSH:-}" ]; then
    echo "Full-repo mutation is forbidden inside git hooks; rerun manually with --full outside the hook." >&2
    return 2
  fi
}

mutation_diff_file() {
  if [ "$MUTATION_MODE" = "full" ]; then
    MUTATION_DIFF_FILE=""
    export MUTATION_DIFF_FILE
    return 0
  fi
  MUTATION_DIFF_FILE="$(mktemp)"
  base="$(git merge-base "$MUTATION_DIFF_REF" HEAD 2>/dev/null || true)"
  if [ -z "$base" ]; then
    echo "[mutation] warning: diff ref $MUTATION_DIFF_REF unavailable; using staged diff" >&2
    git diff --cached --binary > "$MUTATION_DIFF_FILE"
  else
    git diff --binary "$base" HEAD > "$MUTATION_DIFF_FILE"
  fi
  export MUTATION_DIFF_FILE
}

mutation_log() {
  tool="$1"
  mutants="${2:-unknown}"
  echo "[mutation] tool=$tool mode=$MUTATION_MODE mutants=$mutants subsystem=$MUTATION_SUBSYSTEM workers=${3:-unknown} schemata=$MUTATION_SCHEMATA coverage=$MUTATION_COVERAGE" >&2
}
