#!/usr/bin/env bash
# Rust line-coverage gate (cargo-llvm-cov) over every Rust workspace.
#
# Measures line coverage for BOTH Rust workspaces:
#   - /repo/services/speccheck   (the SpecCheck detectors crate)
#   - /repo/rust                 (the PyO3 hot-path kernels workspace)
#
# Coverage tool: cargo-llvm-cov (LLVM source-based coverage via the
# llvm-tools-preview rustup component). Both are baked into the compiled-tools
# image by tools/mutation/Dockerfile.
#
# RATCHET, NOT A CLIFF (phase E8 of docs/PYTHON-RUST-MIGRATION-PLAN.md):
# the long-term target is 95% line coverage, but this gate must NOT hard-fail a
# commit just because current coverage is still below 95% — that would block all
# Rust work until 95% is reached. Instead it enforces a per-workspace FLOOR that
# can only rise: a run passes when each workspace's measured coverage is >= its
# stored floor (minus a tiny tolerance), and the floor is bumped up toward 95%
# whenever coverage improves. The floor never exceeds 95% (the E8 target). The
# floor store is config/rust-coverage-floor.json (committed, shared across
# machines). A drop below the stored floor is the only failure.
set -euo pipefail

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"

# Re-exec into the Docker-managed compiled-tools container when run on the host.
if [[ "${XF_QUALITY_INNER:-0}" != "1" && ! -f /.dockerenv ]]; then
  cd "$repo_root"
  docker compose up -d compiled-tools
  exec docker compose exec -T \
    -e XF_QUALITY_INNER=1 \
    -e RUST_WORKSPACES="${RUST_WORKSPACES:-}" \
    -e RUST_COVERAGE_TARGET="${RUST_COVERAGE_TARGET:-95}" \
    compiled-tools bash /repo/scripts/run-rust-coverage.sh "$@"
fi

# The 95% E8 target the floor ratchets toward (the floor never exceeds this).
RUST_COVERAGE_TARGET="${RUST_COVERAGE_TARGET:-95}"
# Tolerance (percentage points) so floating-point noise in a re-measure of the
# same code does not flip an unchanged workspace from pass to fail.
RUST_COVERAGE_TOLERANCE="${RUST_COVERAGE_TOLERANCE:-0.5}"

default_workspaces="/repo/services/speccheck /repo/rust"
if [[ -n "${RUST_WORKSPACES:-}" ]]; then
  read -r -a workspaces <<< "$RUST_WORKSPACES"
else
  read -r -a workspaces <<< "$default_workspaces"
fi

floor_file="${RUST_COVERAGE_FLOOR_FILE:-$repo_root/config/rust-coverage-floor.json}"
[[ -f "$floor_file" ]] || echo '{}' > "$floor_file"

# Measure one workspace and print its line-coverage percent (a bare number).
measure_workspace() {
  local workspace="$1"
  cd "$workspace"
  # --summary-only --json gives a machine-readable totals block; we read the
  # line-coverage percent from .data[0].totals.lines.percent.
  cargo llvm-cov --workspace --summary-only --json --output-path /tmp/rust-llvm-cov.json \
    >/dev/null 2>&1 || return 1
  python3 - "$workspace" <<'PY'
import json, sys
data = json.load(open("/tmp/rust-llvm-cov.json"))
pct = data["data"][0]["totals"]["lines"]["percent"]
print(f"{pct:.2f}")
PY
}

overall_status=0
for workspace in "${workspaces[@]}"; do
  if [[ ! -f "$workspace/Cargo.toml" ]]; then
    echo "[run-rust-coverage] No Rust workspace at $workspace -- skipping."
    continue
  fi
  echo "[run-rust-coverage] === workspace: $workspace (target ${RUST_COVERAGE_TARGET}%) ==="
  if ! coverage="$(measure_workspace "$workspace")"; then
    echo "FAIL: cargo llvm-cov could not measure coverage for $workspace"
    overall_status=1
    continue
  fi

  # Read the stored floor for this workspace (default 0 the first time), compare
  # with tolerance, then ratchet the floor up toward the target.
  read -r status new_floor < <(python3 - \
      "$floor_file" "$workspace" "$coverage" \
      "$RUST_COVERAGE_TARGET" "$RUST_COVERAGE_TOLERANCE" <<'PY'
import json, sys
floor_file, key, coverage, target, tol = sys.argv[1:6]
coverage = float(coverage); target = float(target); tol = float(tol)
store = json.load(open(floor_file))
floor = float(store.get(key, 0.0))
# Pass when coverage holds at or above the stored floor (within tolerance).
ok = coverage + tol >= floor
# Ratchet: the new floor is the higher of the old floor and the measured
# coverage, but never above the E8 target (so the gate never demands >95%).
new_floor = min(max(floor, coverage), target)
store[key] = round(new_floor, 2)
json.dump(store, open(floor_file, "w"), indent=2, sort_keys=True)
open(floor_file, "a").write("\n")
print("PASS" if ok else "FAIL", round(new_floor, 2))
PY
)

  printf '[run-rust-coverage] %s: line coverage %.2f%% (floor now %s%%, target %s%%)\n' \
    "$workspace" "$coverage" "$new_floor" "$RUST_COVERAGE_TARGET"
  if [[ "$status" != "PASS" ]]; then
    echo "FAIL: $workspace coverage ${coverage}% dropped below its ratchet floor."
    echo "      The floor can only rise. Restore coverage or fix the regression."
    overall_status=1
  fi
done

exit "$overall_status"
