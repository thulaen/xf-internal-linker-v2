#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

# capture-compiler-warnings.sh (Phase B)
#
# Purpose: a small, reusable wrapper that runs a compiler or linter command,
# captures the command's combined stdout+stderr (the warning output) into a
# per-language log file, and then passes the command's real exit code straight
# through so callers (and CI gates) still see pass/fail correctly.
#
# The captured log is the input that
#   python manage.py ingest_compiler_warnings --path <log> --language <lang>
# reads later to turn compiler warnings into tracked findings. This script only
# captures; it never ingests and never changes the command's exit status.
#
# Usage:
#   bash scripts/capture-compiler-warnings.sh <language> <command...>
#   where <language> is one of: cpp | go | rust | haskell
#
# Example:
#   bash scripts/capture-compiler-warnings.sh cpp g++ -Wall -c foo.cpp
#
# Log path: backend/reports/compiler-warnings/<language>.log

usage() {
  cat >&2 <<'EOF'
Usage: bash scripts/capture-compiler-warnings.sh <language> <command...>
  <language>   one of: cpp | go | rust | haskell
  <command...> the compiler/linter command to run; its combined stdout+stderr
               is saved to backend/reports/compiler-warnings/<language>.log and
               its real exit code is passed through.
EOF
}

# Need at least a language plus one command word.
if [[ "$#" -lt 2 ]]; then
  usage
  exit 2
fi

language="$1"
shift

case "$language" in
  cpp | go | rust | haskell) ;;
  *)
    echo "[capture-compiler-warnings] error: invalid language '$language' (expected cpp|go|rust|haskell)" >&2
    usage
    exit 2
    ;;
esac

# Repo root is two levels up from this script (scripts/ -> repo root), matching
# how the other quality scripts locate the tree without depending on the caller's
# current directory.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

log_dir="$repo_root/backend/reports/compiler-warnings"
log="$log_dir/${language}.log"
mkdir -p "$log_dir"

# Run the command, teeing combined stdout+stderr to the log. pipefail plus
# PIPESTATUS[0] let us recover the COMMAND's exit code rather than tee's, so a
# failing compiler is reported as a failure even though tee itself succeeds.
set -o pipefail
"$@" 2>&1 | tee "$log"
rc="${PIPESTATUS[0]}"

# Best-effort line count for the summary; never let it change the exit code.
lines="$(wc -l < "$log" 2>/dev/null | tr -d '[:space:]' || true)"
lines="${lines:-0}"

echo "[capture-compiler-warnings] ${language}: rc=${rc} log=${log} lines=${lines}"

exit "$rc"
