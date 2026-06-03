#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/_quality_concurrency.sh

fail_local_control_plane_context() {
  echo "Lua quality is local-control-plane work and must run through Windows Docker Desktop context desktop-linux." >&2
  echo "Unset remote DOCKER_HOST/DOCKER_CONTEXT values such as Mint, Dell, TCP, or SSH Docker contexts before retrying." >&2
  exit 2
}

ensure_local_control_plane_docker() {
  if [[ "${XF_LUA_QUALITY_IN_CONTAINER:-0}" == "1" ]]; then
    return
  fi

  local docker_context="${DOCKER_CONTEXT:-}"
  local docker_host="${DOCKER_HOST:-}"
  local context_lc="${docker_context,,}"
  local host_lc="${docker_host,,}"

  if [[ -n "$docker_host" ]]; then
    case "$host_lc" in
      tcp://10.10.10.91:2376*|tcp://192.168.0.91:2376*|ssh://*|*mint*|*dell*)
        fail_local_control_plane_context
        ;;
      *)
        fail_local_control_plane_context
        ;;
    esac
  fi

  if [[ -n "$docker_context" && "$context_lc" != "desktop-linux" ]]; then
    fail_local_control_plane_context
  fi

  export DOCKER_CONTEXT=desktop-linux
}

mode="staged"
full_scope=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --full)
      full_scope=1
      shift
      ;;
    --mode)
      mode="${2:-staged}"
      shift 2
      ;;
    *)
      echo "Unknown run-lua-quality option: $1" >&2
      exit 2
      ;;
  esac
done

lua_roots=(
  apps/content/format_filters
  apps/suggestions/anchor_shapes
  apps/governance/lua_runtime
  apps/governance/redis_scripts
  frontend/nginx-lua
  .githooks/lua
)

lua_file_filter='\.lua$'
existing_roots=()
for root in "${lua_roots[@]}"; do
  [[ -d "$root" ]] && existing_roots+=("$root")
done

if [[ "${#existing_roots[@]}" -eq 0 ]]; then
  echo "No Lua roots found."
  exit 0
fi

if [[ "$full_scope" -eq 1 || "${XF_LUA_QUALITY_SCOPE:-scoped}" == "full" ]]; then
  mapfile -t lua_files < <(find "${existing_roots[@]}" -name '*.lua' -type f | sort)
else
  mapfile -t lua_files < <(
    if [[ -n "${COMMIT_SCOPE_PATHS:-}" ]]; then
      printf "%s\n" "$COMMIT_SCOPE_PATHS"
    else
      python scripts/commit_scope.py paths --mode "$mode"
    fi |
      grep -E "$lua_file_filter" |
      grep -E '^(apps/|frontend/nginx-lua/|\.githooks/lua/|services/.*/lua/)' |
      sort -u
  )
fi

if [[ "${#lua_files[@]}" -eq 0 ]]; then
  echo "No scoped Lua files found."
  exit 0
fi

if [[ "${XF_LUA_QUALITY_IN_CONTAINER:-0}" != "1" ]]; then
  ensure_local_control_plane_docker
  quality_install_cleanup_trap
  quality_acquire_meta_lock
  quality_acquire_tool_lock lua-quality
  lua_scope="$(printf "%s\n" "${lua_files[@]}")"
  quality_docker_compose_run lua-quality lua-quality-tools \
    -e COMMIT_SCOPE_PATHS="$lua_scope" \
    -e XF_LUA_QUALITY_IN_CONTAINER=1 \
    -- bash scripts/run-lua-quality.sh --mode "$mode"
  exit $?
fi

workers="$(quality_cores busted)"

printf "%s\n" "${lua_files[@]}" | xargs -r -P "$workers" luacheck --config .luacheckrc
printf "%s\n" "${lua_files[@]}" | xargs -r -P "$workers" -n 1 luajit -bl >/dev/null
if ! command -v lua-fastcheck >/dev/null 2>&1; then
  echo "lua-fastcheck binary is required. Rebuild lua-quality-tools; no alternate checker is allowed." >&2
  exit 2
fi
if ! command -v lua-mutmut >/dev/null 2>&1; then
  echo "lua-mutmut binary is required. Rebuild lua-quality-tools; no alternate checker is allowed." >&2
  exit 2
fi
if ! command -v luamut >/dev/null 2>&1; then
  echo "luamut compatibility command is required. Rebuild lua-quality-tools; no alternate checker is allowed." >&2
  exit 2
fi
lua-fastcheck "${lua_files[@]}"
luamut --version >/dev/null

test_files=()
mutation_sources=()
for path in "${lua_files[@]}"; do
  if [[ "$path" == */tests/*_spec.lua ]]; then
    test_files+=("$path")
    continue
  fi
  base="${path%.lua}"
  candidate="$(dirname "$path")/tests/$(basename "$base")_spec.lua"
  if [[ -f "$candidate" ]]; then
    test_files+=("$candidate")
    mutation_sources+=("$path")
  fi
done

if [[ "${#test_files[@]}" -gt 0 ]]; then
  mapfile -t test_files < <(printf "%s\n" "${test_files[@]}" | sort -u)
  echo "[lua_quality] tool=busted workers=$workers note=\"busted 2.2.0 has no --jobs flag; workers are audited for parallel-safe callers\""
  busted --helper scripts/lua_busted_helper.lua "${test_files[@]}"
  busted --coverage --helper scripts/lua_busted_helper.lua "${test_files[@]}"
  mkdir -p reports/lua
  luacov-cobertura -o reports/lua/coverage.xml
fi

if [[ "${#mutation_sources[@]}" -gt 0 && "${#test_files[@]}" -gt 0 ]]; then
  lua_mutation_args=(
    --report reports/lua/mutation.json
    --helper scripts/lua_busted_helper.lua
  )
  for test_file in "${test_files[@]}"; do
    lua_mutation_args+=(--test "$test_file")
  done
  lua_mutation_args+=(--)
  lua_mutation_args+=("${mutation_sources[@]}")
  lua-mutmut "${lua_mutation_args[@]}"
fi
