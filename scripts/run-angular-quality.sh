#!/usr/bin/env bash
# Angular quality — runs on DELL ONLY, scoped to changed/new frontend files.
#
# Mirrors run-rust-quality.sh's self-sync-to-Dell, fail-CLOSED pattern: the
# changed frontend source is tarred into a Dell volume, then eslint + stylelint
# + ng test (karma-parallel) + Stryker run inside the
# xf-linker-frontend-mutation-tools image on Dell. Dell is REQUIRED — there is
# no Windows fallback. ng test parallelism (karma-parallel executors) and
# Stryker concurrency are both capped at 16 cores (Dell is a 20-thread
# i5-13500T). Set ANGULAR_CORES to override.
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$repo_root"

# Resolve python: the git-hook gate exposes `python`, but a stripped child PATH
# may not — fall back to python3 then known Windows locations so the runner is
# portable across shells.
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
ANGULAR_CORES="${ANGULAR_CORES:-16}"
[[ "$ANGULAR_CORES" -gt 16 ]] && ANGULAR_CORES=16
ANGULAR_VOLUME="${ANGULAR_VOLUME:-xf_angular_repo}"
IMAGE="xf-linker-frontend-mutation-tools:latest"

. scripts/_dell_only_guard.sh
xf_require_remote_context run-angular-quality "$ANGULAR_DOCKER_CONTEXT"

# ── Scope to changed / new frontend files ────────────────────────────────────
scope_mode="${COMMIT_SCOPE_MODE:-staged}"
changed_files="$("$PY" scripts/commit_scope.py paths --mode "$scope_mode" || true)"

lint_targets="$(printf '%s\n' "$changed_files" \
  | grep -E '^frontend/src/app/.*\.(ts|html)$' | sed 's#^frontend/##' || true)"
scss_targets="$(printf '%s\n' "$changed_files" \
  | grep -E '^frontend/src/app/.*\.scss$' | sed 's#^frontend/##' || true)"
# A changed spec is tested directly; ANY other changed src/app .ts file
# (component, service, directive, pipe, plain util/model/routes — anything)
# pulls in its sibling .spec.ts when one exists. The rest of the frontend
# stays skipped — that is the point of scoping.
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

# oxlint lints .ts only — eslint still covers the Angular .html templates.
oxlint_targets="$(printf '%s\n' "$lint_targets" | grep -E '\.ts$' || true)"

if [[ -z "$lint_targets" && -z "$scss_targets" && -z "$test_includes" ]]; then
  echo "[run-angular-quality] No changed frontend file -- skipping."
  exit 0
fi
echo "[run-angular-quality] Scoped to changed frontend files: lint=$(printf '%s' "$lint_targets" | grep -c .) scss=$(printf '%s' "$scss_targets" | grep -c .) test=$(printf '%s' "$test_includes" | grep -c .) (cores=$ANGULAR_CORES)."

# ── Dell is REQUIRED — fail-CLOSED, no Windows fallback ───────────────────────
if ! docker --context "$ANGULAR_DOCKER_CONTEXT" info >/dev/null 2>&1; then
  echo "FAIL run-angular-quality: Dell context '$ANGULAR_DOCKER_CONTEXT' is required and not reachable." >&2
  echo "WHY: Angular quality runs on Dell ONLY; it will not fall back to Windows." >&2
  echo "UNBLOCK: wake/fix the Dell Docker context, then retry the commit." >&2
  exit 1
fi

# ── Sync the frontend source into the Dell volume (no node_modules/build) ─────
if ! tar -cf - \
    --exclude='frontend/node_modules' --exclude='frontend/dist' \
    --exclude='frontend/.angular' --exclude='frontend/coverage' \
    --exclude='frontend/reports' --exclude='frontend/.stryker-tmp' \
    frontend \
    | docker --context "$ANGULAR_DOCKER_CONTEXT" run --rm -i \
        -v "$ANGULAR_VOLUME":/work \
        alpine:latest sh -c "rm -rf /work/frontend && tar -xf - -C /work"; then
  echo "FAIL run-angular-quality: could not sync frontend source to Dell." >&2
  exit 1
fi

# ── Run lint + parallel tests + mutation inside the frontend image on Dell ────
lint_oneline="$(printf '%s' "$lint_targets" | tr '\n' ' ')"
oxlint_oneline="$(printf '%s' "$oxlint_targets" | tr '\n' ' ')"
scss_oneline="$(printf '%s' "$scss_targets" | tr '\n' ' ')"
test_oneline="$(printf '%s' "$test_includes" | tr '\n' ' ')"

exec docker --context "$ANGULAR_DOCKER_CONTEXT" run --rm \
  -v "$ANGULAR_VOLUME":/work \
  -w /work/frontend \
  -e CI=true \
  -e CHROME_BIN=/usr/bin/chromium \
  -e KARMA_PARALLEL_EXECUTORS="$ANGULAR_CORES" \
  -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
  -e LINT_TARGETS="$lint_oneline" \
  -e OXLINT_TARGETS="$oxlint_oneline" \
  -e SCSS_TARGETS="$scss_oneline" \
  -e TEST_INCLUDES="$test_oneline" \
  -e STRYKER_CONCURRENCY="$ANGULAR_CORES" \
  "$IMAGE" sh -lc '
  set -eu
  # The image baked node_modules at /app; the synced source has none. Symlink
  # it so ng / stryker / eslint / stylelint resolve their toolchain + .bin.
  ln -sfn /app/node_modules /work/frontend/node_modules
  # oxlint first: the baked global binary catches most lint issues in
  # milliseconds and fails the gate fast. Default rules + correctness denied;
  # warnings are errors. eslint still runs after it — oxlint is an
  # accelerator, not a replacement for the type-aware eslint rules.
  if [ -n "${OXLINT_TARGETS:-}" ]; then
    echo "+ oxlint $OXLINT_TARGETS"
    oxlint -D correctness --deny-warnings $OXLINT_TARGETS
  fi
  if [ -n "${LINT_TARGETS:-}" ]; then
    echo "+ eslint $LINT_TARGETS"; npx eslint $LINT_TARGETS
  fi
  if [ -n "${SCSS_TARGETS:-}" ]; then
    echo "+ stylelint $SCSS_TARGETS"; npx stylelint $SCSS_TARGETS
  fi
  if [ -n "${TEST_INCLUDES:-}" ]; then
    echo "+ ng test (karma-parallel x$KARMA_PARALLEL_EXECUTORS) --include $TEST_INCLUDES"
    npm run test:ci -- --code-coverage=true --include $TEST_INCLUDES
  fi
  '
