#!/usr/bin/env bash
# Adaptive worker-count policy for local quality tools.
#
# Default behaviour is "use every visible logical CPU". `XF_QUALITY_CORES`
# may request a smaller count and is clamped to the visible CPU count.

quality_platform() {
  case "$(uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]')" in
    darwin*) echo "darwin" ;;
    mingw*|msys*|cygwin*) echo "windows" ;;
    *) echo "linux" ;;
  esac
}

quality_visible_cpus() {
  local platform
  platform="$(quality_platform)"
  local count=""
  if [ "$platform" = "linux" ]; then
    if command -v nproc >/dev/null 2>&1; then
      count="$(nproc 2>/dev/null || true)"
    fi
    if [ -z "$count" ]; then
      count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
    fi
    if [ -r /sys/fs/cgroup/cpu.max ]; then
      local quota period quota_count
      read -r quota period < /sys/fs/cgroup/cpu.max || true
      if [ "${quota:-max}" != "max" ] && [ "${period:-0}" -gt 0 ] 2>/dev/null; then
        quota_count=$(( quota / period ))
        [ "$quota_count" -lt 1 ] && quota_count=1
        if [ -n "$count" ] && [ "$quota_count" -lt "$count" ] 2>/dev/null; then
          count="$quota_count"
        fi
      fi
    fi
  elif command -v sysctl >/dev/null 2>&1; then
    count="$(sysctl -n hw.logicalcpu 2>/dev/null || true)"
  elif command -v powershell.exe >/dev/null 2>&1; then
    count="$(powershell.exe -NoProfile -Command '[Environment]::ProcessorCount' 2>/dev/null | tr -d '\r' || true)"
  fi
  if [ -z "$count" ] || ! [[ "$count" =~ ^[0-9]+$ ]] || [ "$count" -lt 1 ]; then
    echo "[quality_cores] warning: cpu count unavailable; using 1" >&2
    count=1
  fi
  echo "$count"
}

quality_cores() {
  local tool="${1:-quality}"
  local visible requested source workers platform
  platform="$(quality_platform)"
  visible="$(quality_visible_cpus)"
  requested="${XF_QUALITY_CORES:-}"
  source="default"
  workers="$visible"
  if [ -n "$requested" ]; then
    if [[ "$requested" =~ ^[0-9]+$ ]] && [ "$requested" -gt 0 ]; then
      if [ "$requested" -gt "$visible" ]; then
        workers="$visible"
        source="override-clamped"
        echo "[quality_cores] warning: XF_QUALITY_CORES=${requested} clamped to visible_cpus=${visible}" >&2
      else
        workers="$requested"
        source="override"
      fi
    else
      echo "[quality_cores] warning: invalid XF_QUALITY_CORES='${requested}' ignored" >&2
    fi
  fi
  [ "$workers" -lt 1 ] 2>/dev/null && workers=1
  export QUALITY_CORES="$workers"
  export QUALITY_CORES_SOURCE="$source"
  export QUALITY_CORES_VISIBLE_CPUS="$visible"
  export QUALITY_CORES_PLATFORM="$platform"
  echo "[quality_cores] tool=${tool} workers=${workers} source=${source} visible_cpus=${visible} platform=${platform}" >&2
  echo "$workers"
}

quality_log_cores() {
  quality_cores "$1" >/dev/null
}

quality_available_memory_mb() {
  if [ -r /proc/meminfo ]; then
    awk '/MemAvailable:/ {printf "%d\n", $2 / 1024}' /proc/meminfo
    return
  fi
  if command -v sysctl >/dev/null 2>&1; then
    local bytes
    bytes="$(sysctl -n hw.memsize 2>/dev/null || true)"
    if [[ "$bytes" =~ ^[0-9]+$ ]]; then
      echo $(( bytes / 1024 / 1024 ))
      return
    fi
  fi
  echo 0
}

quality_warn_low_memory_per_worker() {
  local tool="$1"
  local workers="$2"
  local available per_worker
  available="$(quality_available_memory_mb)"
  if [ "$available" -le 0 ] 2>/dev/null || [ "$workers" -le 0 ] 2>/dev/null; then
    return
  fi
  per_worker=$(( available / workers ))
  if [ "$per_worker" -lt 1024 ]; then
    echo "[quality_cores] warning: tool=${tool} workers=${workers} available_ram_mb=${available} per_worker_ram_mb=${per_worker} below 1024; proceeding at requested throughput" >&2
  fi
}
