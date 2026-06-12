#!/usr/bin/env bash
# Angular mutation — runs on DELL ONLY, scoped to changed/new frontend files.
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$repo_root"

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

scope_mode="${COMMIT_SCOPE_MODE:-staged}"
changed_files="$("$PY" scripts/commit_scope.py paths --mode "$scope_mode" || true)"

test_includes="$(
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    rel="${path#frontend/}"
    if [[ "$rel" == *.spec.ts ]]; then printf '%s\n' "$rel"; continue; fi
    case "$rel" in
      src/app/*.component.ts|src/app/*.service.ts|src/app/*.directive.ts|src/app/*.pipe.ts)
        spec="${rel%.ts}.spec.ts"; [[ -f "frontend/$spec" ]] && printf '%s\n' "$spec" ;;
      src/app/*.component.html|src/app/*.component.scss)
        spec="${rel%.component.*}.component.spec.ts"; [[ -f "frontend/$spec" ]] && printf '%s\n' "$spec" ;;
    esac
  done <<< "$changed_files" | sort -u
)"

if [[ -z "$test_includes" ]]; then
  echo "[run-angular-mutation] No changed frontend spec files -- skipping."
  exit 0
fi
echo "[run-angular-mutation] Scoped to changed frontend files: test=$(printf '%s' "$test_includes" | grep -c .) (cores=$ANGULAR_CORES)."

if ! docker --context "$ANGULAR_DOCKER_CONTEXT" info >/dev/null 2>&1; then
  echo "FAIL run-angular-mutation: Dell context '$ANGULAR_DOCKER_CONTEXT' is required and not reachable." >&2
  exit 1
fi

if ! tar -cf - \
    --exclude='frontend/node_modules' --exclude='frontend/dist' \
    --exclude='frontend/.angular' --exclude='frontend/coverage' \
    --exclude='frontend/reports' --exclude='frontend/.stryker-tmp' \
    frontend \
    | docker --context "$ANGULAR_DOCKER_CONTEXT" run --rm -i \
        -v "$ANGULAR_VOLUME":/work \
        alpine:latest sh -c "rm -rf /work/frontend && tar -xf - -C /work"; then
  echo "FAIL run-angular-mutation: could not sync frontend source to Dell." >&2
  exit 1
fi

test_oneline="$(printf '%s' "$test_includes" | tr '\n' ' ')"

exec docker --context "$ANGULAR_DOCKER_CONTEXT" run --rm \
  -v "$ANGULAR_VOLUME":/work \
  -w /work/frontend \
  -e CI=true \
  -e CHROME_BIN=/usr/bin/chromium \
  -e XF_QUALITY_ENV="${XF_QUALITY_ENV:-local}" \
  -e STRYKER_CONCURRENCY="$ANGULAR_CORES" \
  "$IMAGE" sh -lc '
  set -eu
  ln -sfn /app/node_modules /work/frontend/node_modules
  echo "+ stryker run --incremental --concurrency $STRYKER_CONCURRENCY"
  if [ "${XF_QUALITY_ENV:-local}" = "ci" ]; then
    npx stryker run --incremental --concurrency "$STRYKER_CONCURRENCY"
  else
    npx stryker run --incremental --concurrency "$STRYKER_CONCURRENCY" || true
  fi
  '
