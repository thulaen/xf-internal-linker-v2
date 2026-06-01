#!/usr/bin/env bash
# Shared helper: capture compiler/linter stderr into the per-language log the
# compiler-warning ingester reads, then run the ingester non-fatally.
#
# The four language quality runners (run-cpp-quality.sh, run-go-quality.sh,
# run-rust-quality.sh, run-haskell-quality.sh) source this file so the wiring
# stays identical across all of them.
#
# Log path convention (matches scripts/capture-compiler-warnings.sh and the
# ingester's --path argument):
#   backend/reports/compiler-warnings/<language>.log
#
# Ingester command (non-fatal — a failed ingest must NOT fail the quality run):
#   python manage.py ingest_compiler_warnings --path <log> --language <lang>
set -euo pipefail

# Host-relative log path for one language. Callers tee the compiler's
# combined stdout+stderr into this file.
compiler_warnings_log_path() {
  local language="$1"
  echo "backend/reports/compiler-warnings/${language}.log"
}

# Container-relative path (the repo is mounted at /repo inside the backend
# container) used when the ingester runs via docker compose.
compiler_warnings_container_path() {
  local language="$1"
  echo "/repo/backend/reports/compiler-warnings/${language}.log"
}

# Create the log directory and start the log empty for this run.
compiler_warnings_init() {
  local language="$1"
  local log
  log="$(compiler_warnings_log_path "$language")"
  mkdir -p "$(dirname "$log")"
  : >"$log"
}

# Run the compiler-warning ingester over the captured log. Never changes the
# caller's exit status: ingest failures are reported and swallowed so the
# quality run's pass/fail is decided only by the real tools.
compiler_warnings_ingest() {
  local language="$1"
  local host_log container_log
  host_log="$(compiler_warnings_log_path "$language")"
  container_log="$(compiler_warnings_container_path "$language")"
  if [[ ! -s "$host_log" ]]; then
    return 0
  fi
  if [[ "${QUALITY_EVIDENCE_SKIP_IMPORT:-0}" == "1" ]]; then
    echo "[compiler-warnings] ${language}: ingest skipped on remote compute shard." >&2
    return 0
  fi
  set +e
  if [[ "${QUALITY_EVIDENCE_FORCE_DIRECT:-0}" != "1" ]] && command -v docker >/dev/null 2>&1; then
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL="*" docker compose run --rm -T backend \
      python manage.py ingest_compiler_warnings --path "$container_log" --language "$language" \
      || echo "[compiler-warnings] ${language}: ingest failed (non-blocking)." >&2
  else
    local backend_dir="${QUALITY_EVIDENCE_BACKEND_DIR:-/repo/backend}"
    if [[ -f "$backend_dir/manage.py" ]]; then
      ( cd "$backend_dir" && python manage.py ingest_compiler_warnings \
        --path "$container_log" --language "$language" ) \
        || echo "[compiler-warnings] ${language}: ingest failed (non-blocking)." >&2
    else
      echo "[compiler-warnings] ${language}: ingest needs Docker or ${backend_dir}/manage.py; skipped (non-blocking)." >&2
    fi
  fi
  set -e
  return 0
}
