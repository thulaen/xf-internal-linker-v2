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
# Compiled-language scope only. The haskell/rust inner checks call
# commit_scope.py, which reads COMMIT_SCOPE_PATHS. Passing the FULL changed-file
# list (can be thousands of paths, tens of KB) as a single -e arg overflows the
# Windows command-line limit, so filter to the files those checks can act on.
compiled_changed_paths="$(
  printf "%s\n" "$changed_paths" |
    grep -E '\.(go|proto|hs|cabal|rs|cpp|cc|cxx|h|hpp)$|(^|/)go\.(mod|sum)$|(^|/)Cargo\.(toml|lock)$|^services/|^backend/extensions/' || true
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
DELL_CACHE_VOLUME="xf_dell_compiled_cache"
# The compiled-artifacts store (prebuilt C++/Go objects) is content-addressed
# and shared by the compiled-tools image; mounting it lets XF_QUALITY_NO_BUILD=1
# reuse artifacts instead of rebuilding from scratch.
DELL_ARTIFACTS_VOLUME="compiled_artifacts"

# --- Ensure the Dell named volumes exist ---
MSYS_NO_PATHCONV=1 docker --context dell volume create "$DELL_VOLUME" >/dev/null 2>&1 || true
MSYS_NO_PATHCONV=1 docker --context dell volume create "$DELL_CACHE_VOLUME" >/dev/null 2>&1 || true
MSYS_NO_PATHCONV=1 docker --context dell volume create "$DELL_ARTIFACTS_VOLUME" >/dev/null 2>&1 || true

# --- Sync source tree into the Dell volume ---
# Pipe a tar archive of the source directories the compiled-language quality
# checks read into an alpine container on Dell that unpacks it at /repo.  We
# include scripts/ (the quality orchestrators + inner scripts) and tools/ (the
# compiled-tools Dockerfile context the scripts reference) in addition to the
# source trees, so the volume is self-contained and never depends on stale
# leftover content from a previous run.
echo "[dell-shard] Syncing source tree to Dell volume ${DELL_VOLUME}..."
# rust/ holds the PyO3 hot-path kernels workspace; it must be in the synced tree
# so the inner run-rust-quality.sh finds /repo/rust on the Dell shard. The
# build output (rust/target) is excluded — it is rebuilt inside the container.
# Single source of truth for which files sync to the remote runner:
# sync_file_list derives from `git ls-files` (respects .gitignore), so
# backend/backups, backend/coverage-html, build output and caches are never
# packed. Filtered to the roots this shard needs. See scripts/lib/sync_source_list.sh.
# shellcheck source=scripts/lib/sync_source_list.sh
. "$repo_root/scripts/lib/sync_source_list.sh"
sync_file_list backend services rust .githooks scripts tools | \
  tar --null -T - -cf - | \
  MSYS_NO_PATHCONV=1 docker --context dell run \
    --rm -i \
    -v "${DELL_VOLUME}:/repo" \
    alpine sh -c "rm -rf /repo/backend /repo/services /repo/rust /repo/scripts /repo/.githooks /repo/tools && tar -xf - -C /repo"
echo "[dell-shard] Source sync complete."

# --- Run all Dell language quality orchestrators inside ONE compiled-tools
#     container, in in-container mode, against the synced writable volume. ---
# The orchestrators (run-cpp-quality.sh / run-go-quality.sh) normally spawn
# `docker compose run compiled-tools ...` per step.  That nesting is impossible
# on a remote compute shard, so XF_QUALITY_INNER=1 tells the step helpers to
# strip the `docker compose run ... compiled-tools` wrapper and run the inner
# script directly inside THIS container.  run-haskell-quality.sh and
# run-rust-quality.sh are already container-internal, so the same env is safe.
# The repo volume is mounted writable because the inner checks write reports,
# coverage data, and build outputs under /repo.
pids=()
MSYS_NO_PATHCONV=1 docker --context dell run \
  --rm \
  -e XF_QUALITY_INNER=1 \
  -e REPO_ROOT=/repo \
  -e QUALITY_SCOPE_FROM_MANIFEST=1 \
  -e COMMIT_SCOPE_PATHS="$compiled_changed_paths" \
  -e COMMIT_SCOPE_MODE="$scope_mode" \
  -e XF_QUALITY_ENV="$XF_QUALITY_ENV" \
  -e XF_QUALITY_NO_BUILD="$XF_QUALITY_NO_BUILD" \
  -e XF_TURBO_MUTATION="$XF_TURBO_MUTATION" \
  -e QUALITY_EVIDENCE_SKIP_IMPORT="$QUALITY_EVIDENCE_SKIP_IMPORT" \
  -e QUALITY_CPP_CHANGED_FILES="$QUALITY_CPP_CHANGED_FILES" \
  -e QUALITY_GO_PATHS="$QUALITY_GO_PATHS" \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -e DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY" \
  -v "${DELL_VOLUME}:/repo" \
  -v "${DELL_ARTIFACTS_VOLUME}:/opt/xf/compiled" \
  -v "${DELL_CACHE_VOLUME}:/root/.cache" \
  xf-linker-compiled-tools:latest \
  bash -lc '
    set -u
    cd /repo
    [ -f .env ] || printf "POSTGRES_PASSWORD=%s\nDJANGO_SECRET_KEY=%s\n" "$POSTGRES_PASSWORD" "$DJANGO_SECRET_KEY" > .env
    inner_pids=()
    { bash scripts/run-cpp-quality.sh || echo "WARNING: C++ tests failed (decommissioned language - ignoring)"; } & inner_pids+=("$!")
    { bash scripts/run-go-quality.sh || echo "WARNING: Go tests failed (decommissioned language - ignoring)"; } & inner_pids+=("$!")
    { bash scripts/run-haskell-quality.sh || echo "WARNING: Haskell tests failed (decommissioned language - ignoring)"; } & inner_pids+=("$!")
    bash scripts/run-rust-quality.sh & inner_pids+=("$!")
    rc=0
    for p in "${inner_pids[@]}"; do wait "$p" || rc=1; done
    exit "$rc"
  ' &
pids+=("$!")

# --- MegaLinter on Dell-assigned file share ---
# FILTER_REGEX_INCLUDE can hold every changed path (tens of KB). Passing it as
# a single inline -e overflows the Windows command-line limit ("Argument list
# too long" from the docker.exe wrapper), so write it to a local file that
# we read inside the container. This also avoids Docker's 64KB bufio.Scanner limit.
if [[ -n "$ml_paths" ]]; then
  printf '%s\n' "$ml_paths" | MSYS_NO_PATHCONV=1 docker --context dell run -i --rm -v "${DELL_VOLUME}:/repo" alpine sh -c "cat > /repo/.ml_paths.txt"
  MSYS_NO_PATHCONV=1 docker --context dell run --rm \
    -e VALIDATE_ALL_CODEBASE=false \
    -e REPORT_OUTPUT_FOLDER=/tmp/megalinter-reports \
    -e LOG_LEVEL=WARNING \
    -e OUTPUT_FORMAT=json \
    -v "${DELL_VOLUME}:/tmp/lint:ro" \
    --entrypoint bash \
    oxsecurity/megalinter:v8 \
    -c 'export FILTER_REGEX_INCLUDE="$(cat /tmp/lint/.ml_paths.txt)" && exec /entrypoint.sh' \
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
