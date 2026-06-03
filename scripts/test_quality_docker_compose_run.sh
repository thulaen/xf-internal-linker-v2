#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d)"
recording="$tmp_dir/docker-recording.log"

cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

mkdir -p "$tmp_dir/bin"
cat > "$tmp_dir/bin/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "ps" ]]; then
  exit 0
fi
printf '%s\n' "$*" >> "$XF_DOCKER_RECORDING"
SH
chmod +x "$tmp_dir/bin/docker"

export PATH="$tmp_dir/bin:$PATH"
export XF_DOCKER_RECORDING="$recording"

cd "$repo_root"
# shellcheck source=scripts/_quality_concurrency.sh
. scripts/_quality_concurrency.sh

assert_last_line() {
  local expected="$1"
  local actual
  actual="$(tail -n 1 "$recording")"
  if [[ "$actual" != "$expected" ]]; then
    echo "FAIL quality_docker_compose_run expected:" >&2
    echo "  $expected" >&2
    echo "got:" >&2
    echo "  $actual" >&2
    return 1
  fi
}

: > "$recording"
quality_docker_compose_run tool-a backend sh -c "echo hi"
assert_last_line "compose run --rm -T --no-deps --name xf-quality-tool-a backend sh -c echo hi"

quality_docker_compose_run tool-b backend -e VAR=value sh -c "echo hi"
assert_last_line "compose run --rm -T --no-deps --name xf-quality-tool-b -e VAR=value backend sh -c echo hi"

quality_docker_compose_run tool-c backend -e A=1 -v /tmp:/tmp sh -c "echo hi"
assert_last_line "compose run --rm -T --no-deps --name xf-quality-tool-c -e A=1 -v /tmp:/tmp backend sh -c echo hi"

quality_docker_compose_run tool-d backend -e VAR=v -- python -e flag
assert_last_line "compose run --rm -T --no-deps --name xf-quality-tool-d -e VAR=v backend python -e flag"

quality_docker_compose_run tool-e backend python -u script.py
assert_last_line "compose run --rm -T --no-deps --name xf-quality-tool-e backend python -u script.py"

export XF_QUALITY_NO_BUILD=1
quality_docker_compose_run tool-f backend python -u script.py
assert_last_line "compose run --rm -T --no-deps --name xf-quality-tool-f --pull never backend python -u script.py"
unset XF_QUALITY_NO_BUILD

echo "quality_docker_compose_run wrapper tests passed"

# Test that quality_acquire_meta_lock no longer enforces mutual exclusion
test_lock_dir="$tmp_dir/meta_locks"
mkdir -p "$test_lock_dir"
export QUALITY_LOCK_DIR="$test_lock_dir"

# Hold the lock in the background
if command -v flock >/dev/null 2>&1; then
  (
    eval "exec 9>'$QUALITY_LOCK_DIR/meta.lock'"
    flock -n 9
    sleep 2
  ) &
  bg_pid=$!
else
  mkdir -p "$QUALITY_LOCK_DIR/meta.lock.d"
  (
    sleep 2
    rmdir "$QUALITY_LOCK_DIR/meta.lock.d"
  ) &
  bg_pid=$!
fi
sleep 0.2

# This should succeed now because meta_lock is a no-op, but would fail previously
if ! quality_acquire_meta_lock 2>/dev/null; then
  echo "FAIL quality_acquire_meta_lock blocked on held lock" >&2
  kill "$bg_pid" 2>/dev/null || true
  exit 1
fi
kill "$bg_pid" 2>/dev/null || true
echo "quality_acquire_meta_lock no-op test passed"
