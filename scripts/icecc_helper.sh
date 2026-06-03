#!/usr/bin/env bash
# Distributed C++ compilation helper (icecc / Icecream).
# Source this script before calling cmake to enable icecc when available.
#
# Sets ICECC_CMAKE_LAUNCHER_FLAGS (cmake -D flags) and ICECC_JOBS (parallel count).
# Both variables are empty / default when icecc is unavailable — safe no-op.
#
# Spec: docs/specs/fr-icecc-distributed-cpp.md
# Ref: https://cmake.org/cmake/help/latest/variable/CMAKE_LANG_COMPILER_LAUNCHER.html
set -euo pipefail

# Default: no distributed compilation.
ICECC_CMAKE_LAUNCHER_FLAGS=""
# Workers: local core count only.  Raised when icecc is active.
ICECC_JOBS="${ICECC_JOBS:-$(nproc 2>/dev/null || echo 2)}"

if command -v icecc >/dev/null 2>&1 && [[ -n "${ICECC_SCHEDULER:-}" ]]; then
  # icecc is installed AND the scheduler address is known — enable distribution.
  ICECC_CMAKE_LAUNCHER_FLAGS="-DCMAKE_C_COMPILER_LAUNCHER=icecc -DCMAKE_CXX_COMPILER_LAUNCHER=icecc"
  # Raise the job count: local cores + estimated remote cores.
  # ICECC_REMOTE_CORES defaults to 8 (a single Mint machine).
  local_cores="$(nproc 2>/dev/null || echo 2)"
  remote_cores="${ICECC_REMOTE_CORES:-8}"
  ICECC_JOBS=$(( local_cores + remote_cores ))
  echo "[icecc_helper] Distributed compilation enabled." \
       "Scheduler: $ICECC_SCHEDULER  Jobs: $ICECC_JOBS" \
       "(${local_cores} local + ${remote_cores} remote)"
else
  echo "[icecc_helper] icecc not available or ICECC_SCHEDULER not set — local build only." \
       "Jobs: $ICECC_JOBS"
fi

export ICECC_CMAKE_LAUNCHER_FLAGS
export ICECC_JOBS
