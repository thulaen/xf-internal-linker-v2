#!/usr/bin/env bash
# lib-cpp-changed.sh — maps changed C++ source files to the GoogleTest
# binary names that own them. Used by pre-commit (fast band) and
# pre-push (heavy band) to build / run only the test binaries affected
# by the current change set, instead of running every test on every commit.
#
# Usage (echoes one binary name per line, deduped, alphabetically sorted):
#   bash .githooks/lib-cpp-changed.sh                        # uses staged diff
#   bash .githooks/lib-cpp-changed.sh "file1.cpp file2.h"    # uses given list
#
# Mapping is conservative — if a source/header isn't listed, no binary
# is emitted (the caller falls back to "no fast C++ run" which is the
# correct behaviour). Header changes target the same binary as their
# matching .cpp because GoogleTest binaries link the .cpp directly.

_changed_files="${1:-}"
if [ -z "$_changed_files" ]; then
  _changed_files=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -E 'backend/extensions/.*\.(cpp|h)$' || true)
fi

_binaries=""
for f in $_changed_files; do
  bn=$(basename "$f")
  case "$bn" in
    simsearch.cpp|simsearch.h)
      _binaries="$_binaries test_simsearch" ;;
    scoring.cpp|scoring.h)
      _binaries="$_binaries test_scoring" ;;
    passagesim.cpp|passagesim.h)
      _binaries="$_binaries test_passagesim" ;;
    quantemb.cpp|quantemb.h)
      _binaries="$_binaries test_quantemb" ;;
    ivf_index.cpp|ivf_index.h)
      _binaries="$_binaries test_ivf_index" ;;
    streaming_sketches.cpp|streaming_sketches.h)
      _binaries="$_binaries test_streaming_sketches" ;;
    test_simsearch.cpp|test_scoring.cpp|test_passagesim.cpp|test_quantemb.cpp|test_ivf_index.cpp|test_streaming_sketches.cpp)
      _binaries="$_binaries ${bn%.cpp}" ;;
    test_edges_simsearch.cpp|test_edges_scoring.cpp)
      _binaries="$_binaries ${bn%.cpp}" ;;
    *) ;;
  esac
done

echo "$_binaries" | tr ' ' '\n' | sort -u | grep -v '^$' || true
