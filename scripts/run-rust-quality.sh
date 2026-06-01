#!/usr/bin/env bash
set -euo pipefail

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
. "$repo_root/scripts/_quality_concurrency.sh"
. "$repo_root/scripts/quality_cores.sh"
. "$repo_root/scripts/mutation_policy.sh"
. "$repo_root/scripts/_compiler_warnings_lib.sh"
compiler_warnings_init rust
rust_warning_log="$repo_root/$(compiler_warnings_log_path rust)"

workspace="${RUST_WORKSPACE:-$repo_root/services/speccheck}"
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

if [[ ! -f "$workspace/Cargo.toml" ]]; then
  echo "No Rust workspace found at $workspace."
  exit 0
fi

cd "$workspace"
echo "+ cargo fmt --check"
cargo fmt --check
echo "+ cargo clippy --jobs $clippy_workers --workspace --all-targets"
# Tee clippy's combined stdout+stderr into the compiler-warning log for the
# ingester, then ingest the captured diagnostics (non-fatal) BEFORE re-raising
# any clippy failure, so warnings are filed even on a failing clippy run.
# pipefail+PIPESTATUS[0] recovers clippy's real exit code (tee always succeeds).
set +e
set -o pipefail
cargo clippy --jobs "$clippy_workers" --workspace --all-targets 2>&1 | tee -a "$rust_warning_log"
clippy_rc="${PIPESTATUS[0]}"
set -e
( cd "$repo_root" && compiler_warnings_ingest rust )
if [[ "$clippy_rc" -ne 0 ]]; then
  exit "$clippy_rc"
fi
echo "+ cargo test --jobs $workers -- --test-threads $workers"
cargo test --jobs "$workers" -- --test-threads "$workers"
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

RUST_FUZZ_MAX_TIME="${RUST_FUZZ_MAX_TIME:-30}"
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
    echo "[run-rust-quality] No fuzz targets found in workspace -- skipping fuzz."
  fi
else
  echo "[run-rust-quality] cargo-fuzz not installed; skipping fuzz."
fi
