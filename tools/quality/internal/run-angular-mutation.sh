#!/usr/bin/env bash
# Angular mutation — runs on DELL ONLY, scoped to changed/new frontend files.
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$repo_root"

if [[ "${XF_BAZEL_PRIVATE_MUTATION:-0}" != "1" ]]; then
  echo "Bazel is the required quality path; run python scripts/bazel_default.py run //tools/quality:mutation." >&2
  exit 2
fi

PY="python"
if ! command -v "$PY" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then
    PY="python3"
  else
    for _c in "/c/Program Files/Python312/python.exe" "/c/Program Files/Python311/python.exe" "$repo_root/.venv/Scripts/python.exe"; do
      [[ -x "$_c" ]] && { PY="$_c"; break; }
    done
  fi
fi

ANGULAR_DOCKER_CONTEXT="${ANGULAR_DOCKER_CONTEXT:-dell}"
. scripts/quality_cores.sh
ANGULAR_CORES="${ANGULAR_CORES:-$(quality_cores angular-mutation)}"
ANGULAR_VOLUME="${ANGULAR_VOLUME:-xf_angular_repo}"
IMAGE="xf-linker-frontend-mutation-tools:latest"

. scripts/_dell_only_guard.sh
xf_require_remote_context run-angular-mutation "$ANGULAR_DOCKER_CONTEXT"

scope_mode="${COMMIT_SCOPE_MODE:-staged}"
changed_files="$("$PY" scripts/commit_scope.py paths --mode "$scope_mode" || true)"

# Source files to MUTATE: changed, non-spec component/service files (matching the
# stryker.config.json mutate globs) that have a sibling spec to test them.
mutate_targets="$(
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    rel="${path#frontend/}"
    case "$rel" in
      src/app/*.spec.ts) ;;
      src/app/*.component.ts|src/app/*.service.ts)
        spec="${rel%.ts}.spec.ts"; [[ -f "frontend/$spec" ]] && printf '%s\n' "$rel" ;;
    esac
  done <<< "$changed_files" | sort -u
)"

# Specs that COVER those source files (the command runner runs these per mutant).
test_includes="$(
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    rel="${path#frontend/}"
    if [[ "$rel" == *.spec.ts ]]; then printf '%s\n' "$rel"; continue; fi
    case "$rel" in
      src/app/*.ts)
        spec="${rel%.ts}.spec.ts"; [[ -f "frontend/$spec" ]] && printf '%s\n' "$spec" ;;
      src/app/*.component.html|src/app/*.component.scss)
        spec="${rel%.component.*}.component.spec.ts"; [[ -f "frontend/$spec" ]] && printf '%s\n' "$spec" ;;
    esac
  done <<< "$changed_files" | sort -u
)"

if [[ -z "$mutate_targets" ]]; then
  echo "[run-angular-mutation] No changed mutable source (component/service) files -- skipping."
  exit 0
fi
echo "[run-angular-mutation] Scoped: mutate=$(printf '%s' "$mutate_targets" | grep -c .) source file(s), test=$(printf '%s' "$test_includes" | grep -c .) spec(s)."

if ! xf_remote_context_reachable "$ANGULAR_DOCKER_CONTEXT"; then
  echo "FAIL run-angular-mutation: Dell context '$ANGULAR_DOCKER_CONTEXT' is required and not reachable." >&2
  exit 1
fi

if ! tar -cf - \
    --exclude='frontend/node_modules' --exclude='frontend/dist' \
    --exclude='frontend/.angular' --exclude='frontend/coverage' \
    --exclude='frontend/reports' --exclude='frontend/.stryker-tmp' \
    frontend \
    | "$PY" scripts/remote_docker.py --host "$ANGULAR_DOCKER_CONTEXT" -- run --rm -i \
        -v "$ANGULAR_VOLUME":/work \
        alpine:latest sh -c "rm -rf /work/frontend && tar -xf - -C /work"; then
  echo "FAIL run-angular-mutation: could not sync frontend source to Dell." >&2
  exit 1
fi

test_oneline="$(
  while IFS= read -r spec; do
    [[ -n "$spec" ]] || continue
    printf '%s\n' "--include=$spec"
  done <<< "$test_includes" | tr '\n' ' '
)"
mutate_oneline="$(printf '%s' "$mutate_targets" | paste -sd, -)"

mutation_cores="$ANGULAR_CORES"

exec "$PY" scripts/remote_docker.py --host "$ANGULAR_DOCKER_CONTEXT" -- run --rm \
  -v "$ANGULAR_VOLUME":/work \
  -e CI=true \
  -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
  -e ANGULAR_CORES="$ANGULAR_CORES" \
  -e VITEST_MAX_THREADS="$ANGULAR_CORES" \
  -e VITEST_MIN_THREADS="$ANGULAR_CORES" \
  -e STRYKER_CONCURRENCY="$mutation_cores" \
  -e STRYKER_MUTATE="$mutate_oneline" \
  -e STRYKER_TEST_INCLUDES="$test_oneline" \
  "$IMAGE" sh -lc '
  set -eu
  # Overlay the synced source onto the image /app dir, which has a REAL
  # node_modules. The unit-test gate symlinks node_modules into /work, but
  # Strykers per-mutant sandbox copies cannot follow that symlink, so mutation
  # runs from /app where the toolchain resolves. The command runner then runs
  # `npm run test:ci -- $STRYKER_TEST_INCLUDES` (the same Vitest path
  # the unit-test gate uses) against each mutated source file.
  tar -C /work/frontend --exclude=node_modules --exclude=.stryker-tmp \
      --exclude=dist --exclude=.angular -cf - . | tar -C /app -xf -
  cd /app
  echo "+ stryker run --mutate $STRYKER_MUTATE --concurrency $STRYKER_CONCURRENCY"
  npx stryker run --mutate "$STRYKER_MUTATE" --concurrency "$STRYKER_CONCURRENCY"
  '
