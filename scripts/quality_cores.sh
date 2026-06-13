#!/usr/bin/env bash

function quality_cores() {
  local tool="$1"
  # Default to 4 cores if not specified
  echo "4"
}

function quality_warn_low_memory_per_worker() {
  local tool="$1"
  local workers="$2"
  # Dummy function to avoid command not found
  :
}
