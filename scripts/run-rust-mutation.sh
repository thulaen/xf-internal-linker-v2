#!/usr/bin/env bash
set -euo pipefail

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
RUST_MUTATION_DOCKER_CONTEXT="${RUST_MUTATION_DOCKER_CONTEXT:-dell}"
XF_RUST_MUTATION_JOBS="${XF_RUST_MUTATION_JOBS:-16}"
. "$repo_root/scripts/_dell_only_guard.sh"
xf_require_remote_context run-rust-mutation "$RUST_MUTATION_DOCKER_CONTEXT"

if [[ "${XF_QUALITY_INNER:-0}" != "1" && ! -f /.dockerenv ]]; then
  cd "$repo_root"
  rust_mutation_jobs="${XF_RUST_MUTATION_JOBS:-16}"
  host_scope_mode="${COMMIT_SCOPE_MODE:-staged}"
  host_rust_paths="$(python "$repo_root/scripts/commit_scope.py" paths --mode "$host_scope_mode" \
    | grep -E '\.rs$|Cargo\.(toml|lock)$' || true)"
  mkdir -p "$repo_root/.tmp"
  if ! git diff --cached -- services rust > "$repo_root/.tmp/rust-mutation.diff"; then
    : > "$repo_root/.tmp/rust-mutation.diff"
  fi
  if [[ ! -s "$repo_root/.tmp/rust-mutation.diff" ]]; then
    git diff -- services rust > "$repo_root/.tmp/rust-mutation.diff" || true
  fi
  while IFS= read -r rust_path; do
    [[ -z "$rust_path" ]] && continue
    [[ -f "$rust_path" ]] || continue
    if ! git ls-files --error-unmatch "$rust_path" >/dev/null 2>&1; then
      git diff --no-index /dev/null "$rust_path" >> "$repo_root/.tmp/rust-mutation.diff" || true
    fi
  done <<< "$host_rust_paths"
  if ! xf_remote_context_reachable "$RUST_MUTATION_DOCKER_CONTEXT"; then
    echo "[run-rust-mutation] Dell Rust mutation context '$RUST_MUTATION_DOCKER_CONTEXT' is required and is not reachable." >&2
    exit 1
  fi

  sync_roots=(scripts services rust config rust-toolchain.toml docker-compose.yml .tmp/rust-mutation.diff)
  existing_roots=()
  for sync_root in "${sync_roots[@]}"; do
    if [[ -e "$sync_root" ]]; then
      existing_roots+=("$sync_root")
    fi
  done
  if [[ "${#existing_roots[@]}" -eq 0 ]]; then
    exit 1
  fi

  export MSYS_NO_PATHCONV=1
  if ! tar -cf - \
      --exclude=.git \
      --exclude=.mypy_cache \
      --exclude=.pytest_cache \
      --exclude=.ruff_cache \
      --exclude=target \
      --exclude=node_modules \
      --exclude=reports \
      --exclude=audit/inter_model \
      "${existing_roots[@]}" \
      | python scripts/remote_docker.py --host "$RUST_MUTATION_DOCKER_CONTEXT" -- run --rm -i \
          -v xf_rust_mutation_repo:/repo \
          alpine:latest sh -c "rm -rf /repo/scripts /repo/services /repo/rust /repo/config /repo/rust-toolchain.toml /repo/docker-compose.yml && tar -xf - -C /repo"; then
    echo "[run-rust-mutation] Failed to sync source to Dell for Rust mutation." >&2
    exit 1
  fi

  exec python scripts/remote_docker.py --host "$RUST_MUTATION_DOCKER_CONTEXT" -- run --rm \
    -v xf_rust_mutation_repo:/repo \
    -v xf_dell_quality_cache:/tmp/xf-test-cache \
    -v xf_sccache:/sccache \
    -e RUSTC_WRAPPER=sccache \
    -e SCCACHE_DIR=/sccache \
    -w /repo \
    -e XF_QUALITY_INNER=1 \
    -e REPO_ROOT=/repo \
    -e COMMIT_SCOPE_MODE="${COMMIT_SCOPE_MODE:-staged}" \
    -e MUTATION_MODE="${MUTATION_MODE:-scoped}" \
    -e MUTATION_DIFF_FILE=/repo/.tmp/rust-mutation.diff \
    -e XF_TURBO_MUTATION="${XF_TURBO_MUTATION:-0}" \
    -e XF_RUST_MUTATION_JOBS="$rust_mutation_jobs" \
    -e QUALITY_RUST_PATHS="$host_rust_paths" \
    -e RUST_WORKSPACE="${RUST_WORKSPACE:-}" \
    -e RUST_WORKSPACES="${RUST_WORKSPACES:-}" \
    xf-linker-compiled-mutation-tools:latest bash /repo/scripts/run-rust-mutation.sh "$@"
fi

. "$repo_root/scripts/_quality_concurrency.sh"
. "$repo_root/scripts/quality_cores.sh"
. "$repo_root/scripts/mutation_policy.sh"

default_workspaces="/repo/services/speccheck /repo/rust"
if [[ -n "${RUST_WORKSPACE:-}" ]]; then
  workspaces=("$RUST_WORKSPACE")
elif [[ -n "${RUST_WORKSPACES:-}" ]]; then
  read -r -a workspaces <<< "$RUST_WORKSPACES"
else
  read -r -a workspaces <<< "$default_workspaces"
fi

mutation_parse_args "$@"
mutation_refuse_full_in_hook
mutation_diff_file
if [[ "$MUTATION_MODE" = "full" ]]; then
  echo "Full-workspace Rust mutation is disabled; this runner only mutates changed or new files via --in-diff." >&2
  exit 1
fi
fmt_workers="$(quality_cores cargo-fmt)"
rust_mutation_jobs="${XF_RUST_MUTATION_JOBS:-16}"
quality_warn_low_memory_per_worker cargo-mutants "$rust_mutation_jobs"

scope_mode="${COMMIT_SCOPE_MODE:-staged}"
if [[ -n "${QUALITY_RUST_PATHS:-}" ]]; then
  rust_paths="$QUALITY_RUST_PATHS"
else
  rust_paths="$(python "$repo_root/scripts/commit_scope.py" paths --mode "$scope_mode" \
    | grep -E '\.rs$|Cargo\.(toml|lock)$' || true)"
fi
if [[ -z "$rust_paths" ]]; then
  echo "[run-rust-mutation] No changed Rust files detected -- skipping."
  exit 0
fi
rust_file_count="$(echo "$rust_paths" | wc -l | tr -d ' ')"
echo "[run-rust-mutation] Scoped to $rust_file_count changed Rust file(s)."
export QUALITY_RUST_PATHS="$rust_paths"

RUST_FUZZ_MAX_TIME="${RUST_FUZZ_MAX_TIME:-30}"
checked_any=0
for workspace in "${workspaces[@]}"; do
  if [[ ! -f "$workspace/Cargo.toml" ]]; then
    echo "[run-rust-mutation] No Rust workspace at $workspace -- skipping."
    continue
  fi
  checked_any=1
  echo "[run-rust-mutation] === workspace: $workspace ==="
  cd "$workspace"

  pairs_file="/repo/audit/rust-mutation-pairs-$$.txt"
  echo -e "$workspace\t$(echo "$QUALITY_RUST_PATHS" | tr '\n' ' ')" > "$pairs_file"
  if ! python /repo/scripts/quality_cache.py filter-pairs --tool rust-mutation --pairs-file "$pairs_file" | grep -q "$workspace"; then
    echo "[run-rust-mutation] $workspace is fully cached, skipping."
    continue
  fi

  if [[ "${XF_TURBO_MUTATION:-0}" == "1" ]]; then
    echo "[run-rust-mutation] XF_TURBO_MUTATION=1: Rust mutation delegated to turbo coordinator (Dell-only split via turbo_mutation.py)"
  elif command -v cargo-mutants >/dev/null 2>&1; then
    mutation_log cargo-mutants unknown "$rust_mutation_jobs"
    echo "+ cargo mutants --in-diff $MUTATION_DIFF_FILE --jobs $rust_mutation_jobs"
    cargo mutants --in-diff "$MUTATION_DIFF_FILE" --jobs "$rust_mutation_jobs"
  else
    echo "cargo-mutants is required for Rust mutation; install it in xf-linker-compiled-mutation-tools:latest." >&2
    exit 1
  fi

  if command -v cargo-fuzz >/dev/null 2>&1; then
    fuzz_targets="$(cargo +nightly fuzz list 2>/dev/null || true)"
    if [[ -n "$fuzz_targets" ]]; then
      while IFS= read -r target; do
        [[ -z "$target" ]] && continue
        echo "+ cargo +nightly fuzz run $target -- -max_total_time=$RUST_FUZZ_MAX_TIME -jobs=$fmt_workers"
        cargo +nightly fuzz run "$target" -- \
          -max_total_time="$RUST_FUZZ_MAX_TIME" \
          -jobs="$fmt_workers"
      done <<< "$fuzz_targets"
    else
      echo "[run-rust-mutation] No fuzz targets found in $workspace -- skipping fuzz."
    fi
  else
    echo "[run-rust-mutation] cargo-fuzz not installed; skipping fuzz."
  fi
  
  python /repo/scripts/quality_cache.py record-pairs --tool rust-mutation --pairs-file "$pairs_file" --root /repo || true
done

if [[ "$checked_any" -eq 0 ]]; then
  echo "[run-rust-mutation] No Rust workspace present in any of: ${workspaces[*]} -- nothing to check."
fi
