#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:${PATH:-}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

. scripts/quality-evidence-lib.sh
evidence_file="$(quality_evidence_path tool-readiness)"
evidence_container="$(quality_evidence_container_path tool-readiness)"
quality_evidence_init "$evidence_file"
trap 'quality_evidence_finalize "$?" "$evidence_file" "$evidence_container"' EXIT
force_build=0
if [[ "${1:-}" == "--build" ]]; then
  force_build=1
fi

record_readiness() {
  local status="$1"
  local tool="$2"
  local command="$3"
  local summary="$4"
  quality_evidence_write \
    --out "$evidence_file" \
    --check-type tool_readiness \
    --status "$status" \
    --tool-name "$tool" \
    --command "$command" \
    --summary "$summary" \
    --failure-fingerprint "tool-readiness:${tool}:${status}"
}

ensure_image() {
  local service="$1"
  local image="$2"
  if [[ "$force_build" -eq 0 ]] && docker image inspect "$image" >/dev/null 2>&1; then
    record_readiness passed "${service}-image" "docker image inspect ${image}" "Docker image is already present."
    return 0
  fi
  if [[ "${XF_QUALITY_NO_BUILD:-0}" == "1" ]]; then
    record_readiness failed "${service}-image" "docker image inspect ${image}" "Docker image is missing and no-build mode is enabled."
    return 1
  fi
  set +e
  "${PYTHON:-python3}" scripts/smart_build.py --target "$service"
  local status=$?
  set -e
  if [[ "$status" -eq 0 ]]; then
    record_readiness passed "${service}-build" "python scripts/smart_build.py --target ${service}" "Docker image built successfully."
  else
    record_readiness failed "${service}-build" "python scripts/smart_build.py --target ${service}" "Docker image build failed."
    exit "$status"
  fi
}

wait_for_service() {
  local service="$1"
  local label="$2"
  for _ in $(seq 1 45); do
    local container_id
    container_id="$(docker compose ps -q "$service" 2>/dev/null || true)"
    if [[ -n "$container_id" ]]; then
      local status
      status="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      if [[ "$status" == "running healthy" || "$status" == "running " ]]; then
        record_readiness passed "${label}-container" "docker compose ps ${service}" "Container is running."
        return 0
      fi
    fi
    sleep 2
  done
  record_readiness failed "${label}-container" "docker compose ps ${service}" "Container did not become healthy."
  return 1
}

ensure_volume() {
  local volume="$1"
  set +e
  docker volume inspect "${repo_root##*/}_${volume}" >/dev/null 2>&1
  local namespaced_status=$?
  docker volume inspect "$volume" >/dev/null 2>&1
  local direct_status=$?
  set -e
  if [[ "$namespaced_status" -eq 0 || "$direct_status" -eq 0 ]]; then
    record_readiness passed "${volume}-volume" "docker volume inspect ${volume}" "Shared tool cache volume is present."
    return 0
  fi
  record_readiness failed "${volume}-volume" "docker volume inspect ${volume}" "Shared tool cache volume is missing."
  return 1
}

changed_frontend_paths() {
  if [[ -n "${COMMIT_SCOPE_PATHS:-}" ]]; then
    printf "%s\n" "$COMMIT_SCOPE_PATHS"
  else
    "${PYTHON:-python3}" scripts/commit_scope.py paths --mode "${COMMIT_SCOPE_MODE:-staged}"
  fi | grep -E '^frontend/' || true
}

# The Windows backend service runs the `runtime` Dockerfile stage
# (image xf-linker-backend-runtime:latest). The old single `xf-linker-backend:latest`
# tag predates the runtime/quality stage split and is no longer used on Windows
# (only docker-compose-helper.yml on the Mint helper still names it). Check the
# real runtime image so this gate never rebuilds the retired tag.
ensure_image backend xf-linker-backend-runtime:latest
# compiled-tools now runs on the Mint helper (mint-quality profile); Windows
# neither builds nor starts it. Its toolchain is verified on Mint further down
# via the `mint` Docker context, matching the 65/35 split where compiled-language
# quality is Mint's share (docs/specs/fr-mint-quality-tool-placement.md).
ensure_image backend-quality xf-linker-backend-quality:latest

frontend_changed_paths="$(changed_frontend_paths)"
if [[ -n "$frontend_changed_paths" ]]; then
  # frontend-mutation-tools runs on Dell (dell-quality profile) — never starts locally on Windows.
  # Verify it is up on Dell via the docker --context dell path.
  set +e
  docker --context dell inspect xf_linker_frontend_mutation_tools > /dev/null 2>&1
  dell_frontend_status=$?
  set -e
  if [[ "$dell_frontend_status" -eq 0 ]]; then
    record_readiness passed frontend-tools-dell "docker --context dell inspect xf_linker_frontend_mutation_tools" "Frontend mutation container is running on Dell."
  else
    record_readiness failed frontend-tools-dell "docker --context dell inspect xf_linker_frontend_mutation_tools" "frontend-mutation-tools is not running on Dell. Start it with: docker --context dell compose up -d --profile dell-quality frontend-mutation-tools"
    exit "$dell_frontend_status"
  fi
  ensure_volume frontend_tool_cache
else
  record_readiness passed frontend-tools-scope "python scripts/commit_scope.py paths --mode ${COMMIT_SCOPE_MODE:-staged}" "No changed frontend files; frontend mutation readiness skipped."
fi

# Verify the compiled-language toolchain on the Mint helper (not Windows).
# Mint runs the `compiled-tools` container as xf_linker_compiled_tools; we reach
# it through the `mint` Docker context (TLS) the same way the build router does.
set +e
docker --context mint exec xf_linker_compiled_tools bash -lc '
  command -v mutmut >/dev/null  # mutmut 2.x has no --version flag; just verify it is installed
  mull-runner-19 --version
  go version
  command -v go-mutesting >/dev/null
  golangci-lint --version
  gosec -version
  cmake --version
  clang++-19 --version
  clang-format-19 --version
  clang-tidy-19 --version
  llvm-cov-19 --version
  llvm-profdata-19 --version
  cppcheck --version
  include-what-you-use --version
  infer --version
  semgrep --version
'
compiled_status=$?
set -e
if [[ "$compiled_status" -eq 0 ]]; then
  record_readiness passed compiled-tools "docker --context mint exec xf_linker_compiled_tools tool version checks" "Compiled-language quality tools are installed in the Mint compiled-tools container."
else
  record_readiness failed compiled-tools "docker --context mint exec xf_linker_compiled_tools tool version checks" "Mint compiled-tools is unreachable or a compiled-language tool is missing."
  exit "$compiled_status"
fi

if [[ -n "$frontend_changed_paths" ]]; then
  # Verify frontend tools on Dell (container lives in dell-quality profile).
  set +e
  docker --context dell exec xf_linker_frontend_mutation_tools sh -lc '
    node --version
    npm --version
    npx eslint --version
    npx stylelint --version
    npx stryker --version
    npm audit --version
  '
  frontend_status=$?
  set -e
  if [[ "$frontend_status" -eq 0 ]]; then
    record_readiness passed frontend-tools "docker --context dell exec xf_linker_frontend_mutation_tools tool version checks" "Frontend quality tools are installed on Dell."
  else
    record_readiness failed frontend-tools "docker --context dell exec xf_linker_frontend_mutation_tools tool version checks" "A frontend quality tool is missing or broken on Dell."
    exit "$frontend_status"
  fi
fi

# The Python quality tools (ruff, pylint, bandit, pip-audit, safety, coverage,
# mutmut) live ONLY in the `quality` Dockerfile stage (image
# xf-linker-backend-quality:latest), which the `backend-quality` compose
# service runs. The production `backend` service runs the lean `runtime` stage
# and intentionally does NOT carry these tools, so check the quality image.
mapfile -t backend_quality_run_opts < <(quality_docker_run_opts)
set +e
docker compose run --rm -T --no-deps "${backend_quality_run_opts[@]}" backend-quality sh -lc '
  ruff --version
  pylint --version
  bandit --version
  pip-audit --version
  safety --version
  coverage --version
  command -v mutmut >/dev/null  # mutmut 2.x has no --version flag; just verify it is installed
'
backend_status=$?
set -e
if [[ "$backend_status" -eq 0 ]]; then
  record_readiness passed backend-tools "docker compose run --rm backend-quality tool version checks" "Backend quality tools are installed."
else
  record_readiness failed backend-tools "docker compose run --rm backend-quality tool version checks" "A backend quality tool is missing or broken."
  exit "$backend_status"
fi

echo "All required Docker-managed quality tools are installed."
