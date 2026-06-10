#!/usr/bin/env bash
set -euo pipefail

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"

if [[ "${XF_QUALITY_INNER:-0}" != "1" && ! -f /.dockerenv ]]; then
  cd "$repo_root"
  docker compose up -d compiled-tools
  exec docker compose exec -T \
    -e XF_QUALITY_INNER=1 \
    -e COMMIT_SCOPE_MODE="${COMMIT_SCOPE_MODE:-staged}" \
    -e MUTATION_MODE="${MUTATION_MODE:-scoped}" \
    -e XF_TURBO_MUTATION="${XF_TURBO_MUTATION:-0}" \
    -e RUST_WORKSPACE="${RUST_WORKSPACE:-}" \
    -e RUST_WORKSPACES="${RUST_WORKSPACES:-}" \
    compiled-tools bash /repo/scripts/run-rust-quality.sh "$@"
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
workers="$(quality_cores cargo-test)"
clippy_workers="$(quality_cores cargo-clippy)"
fmt_workers="$(quality_cores cargo-fmt)"
mutant_workers="$(quality_cores cargo-mutants)"
quality_warn_low_memory_per_worker cargo-mutants "$mutant_workers"

# Scope guard: skip entirely when no Rust-relevant files changed.
# In CI set COMMIT_SCOPE_MODE=push; locally defaults to staged.
# Matches: *.rs, Cargo.toml, Cargo.lock
scope_mode="${COMMIT_SCOPE_MODE:-staged}"
rust_paths="$(python "$repo_root/scripts/commit_scope.py" paths --mode "$scope_mode" \
  | grep -E '\.rs$|Cargo\.(toml|lock)$' || true)"
if [[ -z "$rust_paths" ]]; then
  echo "[run-rust-quality] No changed Rust files detected -- skipping."
  exit 0
fi
rust_file_count="$(echo "$rust_paths" | wc -l | tr -d ' ')"
echo "[run-rust-quality] Scoped to $rust_file_count changed Rust file(s)."
export QUALITY_RUST_PATHS="$rust_paths"

# Run the fmt + clippy + test + mutation + fuzz block once per workspace. A
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

  if [[ "${XF_TURBO_MUTATION:-0}" == "1" ]]; then
    echo "[run-rust-quality] XF_TURBO_MUTATION=1: Rust mutation delegated to turbo coordinator (65/35 split via turbo_mutation.py)"
  elif command -v cargo-mutants >/dev/null 2>&1; then
    mutation_log cargo-mutants unknown "$mutant_workers"
    if [[ "$MUTATION_MODE" = "full" ]]; then
      echo "+ cargo mutants --jobs $mutant_workers"
      cargo mutants --jobs "$mutant_workers"
    else
      echo "+ cargo mutants --in-diff $MUTATION_DIFF_FILE --jobs $mutant_workers"
      cargo mutants --in-diff "$MUTATION_DIFF_FILE" --jobs "$mutant_workers"
    fi
  else
    echo "cargo-mutants not installed; skipping Rust mutation."
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
      echo "[run-rust-quality] No fuzz targets found in $workspace -- skipping fuzz."
    fi
  else
    echo "[run-rust-quality] cargo-fuzz not installed; skipping fuzz."
  fi
done

if [[ "$checked_any" -eq 0 ]]; then
  echo "[run-rust-quality] No Rust workspace present in any of: ${workspaces[*]} -- nothing to check."
fi
