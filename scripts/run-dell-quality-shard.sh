#!/usr/bin/env bash
# Dell-side quality runner.
# Mirror of run-mint-quality-shard.sh but targets the Dell machine via
# docker --context dell.
#
# Called from precommit-docker.sh in parallel with run-mint-quality-shard.sh.
# Reads the shard manifest from stdin, syncs the source tree to the Dell
# compiled-tools container, runs all Dell-owned quality checks in parallel,
# then returns MegaLinter JSON to stdout.
#
# MSYS_NO_PATHCONV=1 is required on every docker command because this script
# runs on Windows (Git Bash / MSYS2) and the Windows path converter mangles
# Docker volume and context arguments.
set -euo pipefail
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

manifest="$(cat)"  # JSON piped from precommit-docker.sh

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${REPO_ROOT:-$(cd "$script_dir/.." && pwd)}"
cd "$repo_root"

ml_paths="$(printf "%s" "$manifest" | python3 -c '
import json, sys
paths = json.load(sys.stdin).get("dell_megalinter_paths", [])
print("|".join(paths))
')"

workers="$(printf "%s" "$manifest" | python3 -c '
import json, sys
print(json.load(sys.stdin).get("dell_workers", 4))
')"

changed_paths="$(printf "%s" "$manifest" | python3 -c '
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
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-dell-quality-not-used}"
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-dell-quality-dummy-secret-key}"

DELL_VOLUME="xf_dell_compiled_repo"

# --- Ensure the Dell named volume exists ---
MSYS_NO_PATHCONV=1 docker --context dell volume create "$DELL_VOLUME" >/dev/null 2>&1 || true

# --- Sync source tree into the Dell volume ---
# We pipe a tar archive of the three source directories into an alpine
# container on Dell that unpacks it at /repo.  The alpine container is
# lightweight (no build tools) and exits immediately after the unpack.
echo "[dell-shard] Syncing source tree to Dell volume ${DELL_VOLUME}..."
tar -cf - backend services .githooks | \
  MSYS_NO_PATHCONV=1 docker --context dell run \
    --rm -i \
    -v "${DELL_VOLUME}:/repo" \
    alpine sh -c "tar -xf - -C /repo"
echo "[dell-shard] Source sync complete."

# --- Run all Dell language quality checks in parallel ---
pids=()

# C++ quality
MSYS_NO_PATHCONV=1 docker --context dell run \
  --rm -T \
  -e COMMIT_SCOPE_MODE="$scope_mode" \
  -e XF_QUALITY_ENV="$XF_QUALITY_ENV" \
  -e XF_QUALITY_NO_BUILD="$XF_QUALITY_NO_BUILD" \
  -e XF_TURBO_MUTATION="$XF_TURBO_MUTATION" \
  -e QUALITY_CPP_CHANGED_FILES="$QUALITY_CPP_CHANGED_FILES" \
  -v "${DELL_VOLUME}:/repo:ro" \
  xf-linker-compiled-tools:latest \
  bash -lc 'cd /repo && bash scripts/run-cpp-quality.sh' &
pids+=("$!")

# Go quality
MSYS_NO_PATHCONV=1 docker --context dell run \
  --rm -T \
  -e COMMIT_SCOPE_MODE="$scope_mode" \
  -e XF_QUALITY_ENV="$XF_QUALITY_ENV" \
  -e XF_QUALITY_NO_BUILD="$XF_QUALITY_NO_BUILD" \
  -e XF_TURBO_MUTATION="$XF_TURBO_MUTATION" \
  -e QUALITY_GO_PATHS="$QUALITY_GO_PATHS" \
  -v "${DELL_VOLUME}:/repo:ro" \
  xf-linker-compiled-tools:latest \
  bash -lc 'cd /repo && bash scripts/run-go-quality.sh' &
pids+=("$!")

# Haskell quality
MSYS_NO_PATHCONV=1 docker --context dell run \
  --rm -T \
  -e COMMIT_SCOPE_MODE="$scope_mode" \
  -e XF_QUALITY_ENV="$XF_QUALITY_ENV" \
  -e XF_QUALITY_NO_BUILD="$XF_QUALITY_NO_BUILD" \
  -e XF_TURBO_MUTATION="$XF_TURBO_MUTATION" \
  -v "${DELL_VOLUME}:/repo:ro" \
  xf-linker-compiled-tools:latest \
  bash -lc 'cd /repo && bash scripts/run-haskell-quality.sh' &
pids+=("$!")

# Rust quality
MSYS_NO_PATHCONV=1 docker --context dell run \
  --rm -T \
  -e COMMIT_SCOPE_MODE="$scope_mode" \
  -e XF_QUALITY_ENV="$XF_QUALITY_ENV" \
  -e XF_QUALITY_NO_BUILD="$XF_QUALITY_NO_BUILD" \
  -e XF_TURBO_MUTATION="$XF_TURBO_MUTATION" \
  -v "${DELL_VOLUME}:/repo:ro" \
  xf-linker-compiled-tools:latest \
  bash -lc 'cd /repo && bash scripts/run-rust-quality.sh' &
pids+=("$!")

# --- MegaLinter on Dell-assigned file share ---
if [[ -n "$ml_paths" ]]; then
  MSYS_NO_PATHCONV=1 docker --context dell run --rm \
    -e VALIDATE_ALL_CODEBASE=false \
    -e "FILTER_REGEX_INCLUDE=$ml_paths" \
    -e REPORT_OUTPUT_FOLDER=/tmp/megalinter-reports \
    -e LOG_LEVEL=WARNING \
    -e OUTPUT_FORMAT=json \
    -v "${DELL_VOLUME}:/tmp/lint:ro" \
    oxsecurity/megalinter:v8 \
    >> "/tmp/dell-megalinter-$$.jsonl" 2>&1 &
  pids+=("$!")
fi

# --- Wait for all parallel jobs and collect exit codes ---
status=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    status=1
  fi
done

# --- Return MegaLinter output to Windows (via stdout) ---
if [[ -f "/tmp/dell-megalinter-$$.jsonl" ]]; then
  cat "/tmp/dell-megalinter-$$.jsonl"
  rm -f "/tmp/dell-megalinter-$$.jsonl"
fi

exit "$status"
