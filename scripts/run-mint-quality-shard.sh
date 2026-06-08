#!/usr/bin/env bash
# Mint-side quality runner.
# Called via SSH from run-scoped-static-quality.ps1.
# Reads the shard manifest from stdin, runs all Mint-owned quality checks
# in parallel, then returns MegaLinter JSON to stdout.
set -euo pipefail

manifest="$(cat)"  # JSON piped from Windows via SSH

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${REPO_ROOT:-$(cd "$script_dir/.." && pwd)}"
cd "$repo_root"

ml_paths="$(echo "$manifest" | python3 -c '
import json, sys
paths = json.load(sys.stdin).get("mint_megalinter_paths", [])
print("|".join(paths))
')"

workers="$(echo "$manifest" | python3 -c '
import json, sys
print(json.load(sys.stdin).get("mint_workers", 4))
')"

changed_paths="$(echo "$manifest" | python3 -c '
import json, sys
paths = json.load(sys.stdin).get("changed_files", [])
print("\n".join(paths))
')"

export QUALITY_SCOPE_FROM_MANIFEST=1
export QUALITY_CPP_CHANGED_FILES="$(
  printf "%s\n" "$changed_paths" |
    grep -E '^backend/extensions/.*\.(cpp|h)$' || true
)"
export QUALITY_GO_PATHS="$(
  printf "%s\n" "$changed_paths" |
    grep -E '(^|/)go\.(mod|sum)$|\.go$|\.proto$' || true
)"

scope_mode="${COMMIT_SCOPE_MODE:-push}"
export XF_QUALITY_ENV="${XF_QUALITY_ENV:-ci}"
export COMMIT_SCOPE_MODE="$scope_mode"
export XF_QUALITY_NO_BUILD="${XF_QUALITY_NO_BUILD:-1}"
export XF_TURBO_MUTATION="${XF_TURBO_MUTATION:-1}"
export QUALITY_EVIDENCE_SKIP_IMPORT="${QUALITY_EVIDENCE_SKIP_IMPORT:-1}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-mint-quality-not-used}"
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-mint-quality-dummy-secret-key}"

if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  python_bin_dir="/tmp/xf-mint-python-bin"
  mkdir -p "$python_bin_dir"
  ln -sf "$(command -v python3)" "$python_bin_dir/python"
  export PATH="$python_bin_dir:$PATH"
fi
if [[ ! -f "$repo_root/.env" ]]; then
  printf "POSTGRES_PASSWORD=%s\n" "$POSTGRES_PASSWORD" > "$repo_root/.env"
fi
if ! grep -q '^DJANGO_SECRET_KEY=' "$repo_root/.env"; then
  printf "DJANGO_SECRET_KEY=%s\n" "$DJANGO_SECRET_KEY" >> "$repo_root/.env"
fi

# --- Start icecc daemon and scheduler so Windows Docker container can
#     distribute C++ translation units to Mint cores.
#     Spec: docs/specs/fr-icecc-distributed-cpp.md
#     Guard: skip silently when icecc is not installed (graceful fallback).
if command -v icecc-scheduler >/dev/null 2>&1 && command -v iceccd >/dev/null 2>&1; then
  icecc-scheduler --daemon 2>/dev/null || true
  iceccd --daemon 2>/dev/null || true
  echo "[mint-shard] icecc scheduler and daemon started (distributed C++ compilation enabled)."
else
  echo "[mint-shard] icecc not installed - distributed C++ compilation disabled (local fallback)."
fi

# --- Run all Mint language quality checks in parallel ---
pids=()
{ bash "$repo_root/scripts/run-cpp-quality.sh" || echo "WARNING: C++ tests failed (decommissioned language - ignoring)"; } &
pids+=("$!")
{ bash "$repo_root/scripts/run-go-quality.sh" || echo "WARNING: Go tests failed (decommissioned language - ignoring)"; } &
pids+=("$!")
docker exec \
  -e COMMIT_SCOPE_MODE="$scope_mode" \
  -e XF_QUALITY_ENV="$XF_QUALITY_ENV" \
  -e XF_QUALITY_NO_BUILD="$XF_QUALITY_NO_BUILD" \
  -e XF_TURBO_MUTATION="$XF_TURBO_MUTATION" \
  xf_linker_compiled_tools \
  bash -lc 'cd /repo && { bash scripts/run-haskell-quality.sh || echo "WARNING: Haskell tests failed (decommissioned language - ignoring)"; }' &
pids+=("$!")
docker exec \
  -e COMMIT_SCOPE_MODE="$scope_mode" \
  -e XF_QUALITY_ENV="$XF_QUALITY_ENV" \
  -e XF_QUALITY_NO_BUILD="$XF_QUALITY_NO_BUILD" \
  -e XF_TURBO_MUTATION="$XF_TURBO_MUTATION" \
  xf_linker_compiled_tools \
  bash -lc 'cd /repo && bash scripts/run-rust-quality.sh' &
pids+=("$!")

# --- MegaLinter on Mint-assigned file share ---
# FILTER_REGEX_INCLUDE can hold every changed path (hundreds of |-joined
# paths, tens of KB). Passing it as a single inline -e overflows the OS
# command-line limit ("Argument list too long" via the docker wrapper), so
# write it to a local file that we read inside the container. This also avoids Docker's 64KB bufio.Scanner limit.
if [[ -n "$ml_paths" ]]; then
  ml_env_file="$(mktemp)"
  printf '%s\n' "$ml_paths" > "$ml_env_file"
  ml_env_file_arg="$ml_env_file"
  command -v cygpath >/dev/null 2>&1 && ml_env_file_arg="$(cygpath -w "$ml_env_file")"
  docker run --rm \
    -e VALIDATE_ALL_CODEBASE=false \
    -e REPORT_OUTPUT_FOLDER=/tmp/megalinter-reports \
    -e LOG_LEVEL=WARNING \
    -e OUTPUT_FORMAT=json \
    -v "$repo_root:/tmp/lint:ro" \
    -v "$ml_env_file_arg:/tmp/ml_paths.txt:ro" \
    --entrypoint bash \
    oxsecurity/megalinter:v8 \
    -c 'export FILTER_REGEX_INCLUDE="$(cat /tmp/ml_paths.txt)" && exec /entrypoint.sh' \
    >> "/tmp/mint-megalinter-$$.jsonl" 2>&1 &
  pids+=("$!")
fi

# --- Wait for all parallel jobs ---
status=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    status=1
  fi
done

# --- Return MegaLinter output to Windows (via SSH stdout) ---
if [[ -f "/tmp/mint-megalinter-$$.jsonl" ]]; then
  cat "/tmp/mint-megalinter-$$.jsonl"
  rm -f "/tmp/mint-megalinter-$$.jsonl"
fi
[[ -n "$ml_env_file" && -f "$ml_env_file" ]] && rm -f "$ml_env_file"
exit "$status"
