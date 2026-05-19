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

echo "quality_docker_compose_run wrapper tests passed"
