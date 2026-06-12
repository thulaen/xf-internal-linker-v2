#!/usr/bin/env bash
set -euo pipefail

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
RUST_MUTATION_DOCKER_CONTEXT="${RUST_MUTATION_DOCKER_CONTEXT:-dell}"
. "$repo_root/scripts/_dell_only_guard.sh"
xf_require_remote_context run-rust-quality "$RUST_MUTATION_DOCKER_CONTEXT"
XF_RUST_MUTATION_JOBS="${XF_RUST_MUTATION_JOBS:-16}"

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
  if [[ -z "$host_rust_paths" && ! -s "$repo_root/.tmp/rust-mutation.diff" ]]; then
    echo "[run-rust-quality] No changed Rust files detected -- skipping Dell sync and Rust quality run."
    exit 0
  fi
  if ! docker --context "$RUST_MUTATION_DOCKER_CONTEXT" info >/dev/null 2>&1; then
    echo "[run-rust-quality] Dell Rust mutation context '$RUST_MUTATION_DOCKER_CONTEXT' is required and is not reachable." >&2
    echo "[run-rust-quality] Fix the Dell Docker context; Rust mutation is compulsory and will not fall back to Windows." >&2
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
    echo "[run-rust-quality] No source roots found to sync for Dell Rust mutation." >&2
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
      | docker --context "$RUST_MUTATION_DOCKER_CONTEXT" run --rm -i \
          -v xf_rust_mutation_repo:/repo \
          alpine:latest sh -c "rm -rf /repo/scripts /repo/services /repo/rust /repo/config /repo/rust-toolchain.toml /repo/docker-compose.yml && tar -xf - -C /repo"; then
    echo "[run-rust-quality] Failed to sync source to Dell for Rust mutation." >&2
    exit 1
  fi

  exec docker --context "$RUST_MUTATION_DOCKER_CONTEXT" run --rm \
    -v xf_rust_mutation_repo:/repo \
    -v xf_dell_quality_cache:/tmp/xf-test-cache \
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
    xf-linker-compiled-mutation-tools:latest bash /repo/scripts/run-rust-quality.sh "$@"
fi

. "$repo_root/scripts/_quality_concurrency.sh"
. "$repo_root/scripts/quality_cores.sh"
. "$repo_root/scripts/mutation_policy.sh"
. "$repo_root/scripts/_compiler_warnings_lib.sh"
compiler_warnings_init rust
rust_warning_log="$repo_root/$(compiler_warnings_log_path rust)"

# Workspace list. Both Rust workspaces are checked by default:
#   - services/speccheck      (the SpecCheck detectors crate)
#   - rust/                   (the PyO3 hot-path kernels workspace)
# A caller can pin the run to a single workspace with RUST_WORKSPACE (legacy,
# singular). RUST_WORKSPACES (plural) overrides the whole list. Paths are
# absolute container paths under /repo; the outer host re-exec maps the working
# tree to /repo, and the Dell shard syncs both trees into its /repo volume.
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
workers="$(quality_cores cargo-test)"
clippy_workers="$(quality_cores cargo-clippy)"
fmt_workers="$(quality_cores cargo-fmt)"
rust_mutation_jobs="${XF_RUST_MUTATION_JOBS:-16}"
quality_warn_low_memory_per_worker cargo-mutants "$rust_mutation_jobs"

# Scope guard: skip entirely when no Rust-relevant files changed.
# In CI set COMMIT_SCOPE_MODE=push; locally defaults to staged.
# Matches: *.rs, Cargo.toml, Cargo.lock
scope_mode="${COMMIT_SCOPE_MODE:-staged}"
if [[ -n "${QUALITY_RUST_PATHS:-}" ]]; then
  rust_paths="$QUALITY_RUST_PATHS"
else
  rust_paths="$(python "$repo_root/scripts/commit_scope.py" paths --mode "$scope_mode" \
    | grep -E '\.rs$|Cargo\.(toml|lock)$' || true)"
fi
if [[ -z "$rust_paths" ]]; then
  echo "[run-rust-quality] No changed Rust files detected -- skipping."
  exit 0
fi
rust_file_count="$(echo "$rust_paths" | wc -l | tr -d ' ')"
echo "[run-rust-quality] Scoped to $rust_file_count changed Rust file(s)."
export QUALITY_RUST_PATHS="$rust_paths"

# Run the fmt + clippy + test block once per workspace. A
# workspace whose Cargo.toml is absent (e.g. only one of the two trees is
# present on a given machine) is SKIPPED with `continue`, never a hard failure:
# the gate only exits non-zero on a real fmt/clippy/test/mutation failure.
RUST_FUZZ_MAX_TIME="${RUST_FUZZ_MAX_TIME:-30}"
checked_any=0
for workspace in "${workspaces[@]}"; do
  if [[ ! -f "$workspace/Cargo.toml" ]]; then
    echo "[run-rust-quality] No Rust workspace at $workspace -- skipping."
    continue
  fi
  checked_any=1
  echo "[run-rust-quality] === workspace: $workspace ==="
  cd "$workspace"

  pairs_file="/repo/audit/rust-quality-pairs-$$.txt"
  echo -e "$workspace\t$(echo "$QUALITY_RUST_PATHS" | tr '\n' ' ')" > "$pairs_file"
  if ! python /repo/scripts/quality_cache.py filter-pairs --tool rust-quality --pairs-file "$pairs_file" | grep -q "$workspace"; then
    echo "[run-rust-quality] $workspace is fully cached, skipping."
    continue
  fi

  echo "+ cargo fmt --check"
  cargo fmt --check
  echo "+ cargo clippy --jobs $clippy_workers --workspace --all-targets -- -D warnings"
  # Tee clippy's combined stdout+stderr into the compiler-warning log for the
  # ingester, then ingest the captured diagnostics (non-fatal) BEFORE re-raising
  # any clippy failure, so warnings are filed even on a failing clippy run.
  # pipefail+PIPESTATUS[0] recovers clippy's real exit code (tee always succeeds).
  set +e
  set -o pipefail
  cargo clippy --jobs "$clippy_workers" --workspace --all-targets -- -D warnings 2>&1 \
    | tee -a "$rust_warning_log"
  clippy_rc="${PIPESTATUS[0]}"
  set -e
  ( cd "$repo_root" && compiler_warnings_ingest rust )
  if [[ "$clippy_rc" -ne 0 ]]; then
    exit "$clippy_rc"
  fi

  echo "+ cargo test --jobs $workers -- --test-threads $workers"
  set +e
  set -o pipefail
  cargo test --jobs "$workers" -- --test-threads "$workers" 2>&1 | tee "/tmp/cargo_test_out_$$.log"
  test_rc="${PIPESTATUS[0]}"
  set -e
  if [[ "$test_rc" -ne 0 ]]; then
    echo "[run-rust-quality] Cargo test failed. Filing AutoIssue..."
    # Take the last 20 lines as the summary
    summary="$(tail -n 20 "/tmp/cargo_test_out_$$.log" | tr '\n' ' ')"
    if [[ -z "${summary// /}" ]]; then
      summary="Cargo test failed with exit code $test_rc"
    fi
    # Use python if available to file the issue
    if command -v python >/dev/null 2>&1 && python -c "import django" >/dev/null 2>&1; then
      python "$repo_root/backend/manage.py" file_test_failure \
        --tool "cargo-test" \
        --test-target "workspace:$(basename "$workspace")" \
        --test-file "$workspace" \
        --test-name "cargo-test" \
        --failure-summary "$summary" \
        --severity high \
        --run-id "${XF_QUALITY_RUN_ID:-local-run}" \
        --shard-id "${XF_QUALITY_SHARD_ID:-local-shard}" \
        --worker "${XF_QUALITY_WORKER:-windows}" || true
    else
      echo "[run-rust-quality] python not found, skipping AutoIssue filing."
    fi
    exit "$test_rc"
  fi
  
  python /repo/scripts/quality_cache.py record-pairs --tool rust-quality --pairs-file "$pairs_file" --root /repo || true

done

if [[ "$checked_any" -eq 0 ]]; then
  echo "[run-rust-quality] No Rust workspace present in any of: ${workspaces[*]} -- nothing to check."
fi
