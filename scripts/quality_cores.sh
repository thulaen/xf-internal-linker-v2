#!/usr/bin/env bash

function quality_cores() {
  local tool="${1:-quality}"
  local visible
  local requested="${XF_QUALITY_CORES:-}"
  local source="default"
  local workers
  visible="$(_quality_visible_cpus)"
  workers="$visible"
  if [[ -n "$requested" ]]; then
    if [[ "$requested" =~ ^[0-9]+$ && "$requested" -gt 0 ]]; then
      if [[ "$requested" -gt "$visible" ]]; then
        workers="$visible"
        source="override-clamped"
        echo "[quality_cores] warning: XF_QUALITY_CORES=$requested clamped to visible_cpus=$visible" >&2
      else
        workers="$requested"
        source="override"
      fi
    else
      echo "[quality_cores] warning: invalid XF_QUALITY_CORES='$requested' ignored" >&2
    fi
  fi
  export QUALITY_CORES="$workers"
  export QUALITY_CORES_SOURCE="$source"
  export QUALITY_CORES_VISIBLE_CPUS="$visible"
  export QUALITY_CORES_PLATFORM="$(_quality_platform)"
  echo "[quality_cores] tool=$tool workers=$workers source=$source visible_cpus=$visible platform=$QUALITY_CORES_PLATFORM" >&2
  printf '%s\n' "$workers"
}

function quality_warn_low_memory_per_worker() {
  local tool="$1"
  local workers="$2"
  if [[ "$workers" =~ ^[0-9]+$ && "$workers" -gt 0 ]]; then
    return 0
  fi
  echo "[quality_cores] warning: $tool received invalid worker count '$workers'" >&2
}

function _quality_visible_cpus() {
  local count=""
  if command -v nproc >/dev/null 2>&1; then
    count="$(nproc 2>/dev/null || true)"
  fi
  if [[ -z "$count" ]] && command -v getconf >/dev/null 2>&1; then
    count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
  fi
  if [[ -z "$count" && -n "${NUMBER_OF_PROCESSORS:-}" ]]; then
    count="$NUMBER_OF_PROCESSORS"
  fi
  if [[ ! "$count" =~ ^[0-9]+$ || "$count" -lt 1 ]]; then
    count=1
  fi
  printf '%s\n' "$count"
}

function _quality_platform() {
  local name
  name="$(uname -s 2>/dev/null || printf unknown)"
  case "$name" in
    Darwin*) printf darwin ;;
    MINGW*|MSYS*|CYGWIN*) printf windows ;;
    Linux*) printf linux ;;
    *) printf linux ;;
  esac
}
