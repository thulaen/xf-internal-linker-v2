#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/_quality_concurrency.sh"

build_dir=/tmp/xf-build/cpp-fuzz

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf "$build_dir"
fi

cd /repo/backend/extensions/fuzz
mkdir -p "$build_dir"
cmake -B "$build_dir" -S . \
  -DCMAKE_C_COMPILER=clang-19 \
  -DCMAKE_CXX_COMPILER=clang++-19 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$build_dir" --parallel 2

targets=(
  fuzz_simsearch
  fuzz_scoring
  fuzz_passagesim
  fuzz_quantemb
  fuzz_rareterm
  fuzz_texttok
  fuzz_anchor_descriptiveness
  fuzz_anchor_diversity
  fuzz_anchor_self_information
  fuzz_api_rate_limiter
  fuzz_compressed_bloom
  fuzz_count_min_sketch
  fuzz_counting_bloom
  fuzz_feedrerank
  fuzz_fieldrel
  fuzz_generic_anchor_matcher
  fuzz_ivf_index
  fuzz_l2norm
  fuzz_linkparse
  fuzz_pagerank
  fuzz_phrasematch
)

quality_log_scope_decision "scripts/run-cpp-fuzz-smoke.sh" libFuzzer "runs the fixed smoke binary list for changed native-code safety checks"

for target in "${targets[@]}"; do
  echo "Running ${target}..."
  "$build_dir/$target" -runs=0
done
