#!/usr/bin/env bash

function compiler_warnings_init() {
  local tool="$1"
  mkdir -p "$repo_root/.tmp"
  : > "$repo_root/.tmp/warnings_${tool}.log"
}

function compiler_warnings_log_path() {
  local tool="$1"
  echo ".tmp/warnings_${tool}.log"
}

function compiler_warnings_ingest() {
  local tool="$1"
  # Dummy ingest
  :
}
