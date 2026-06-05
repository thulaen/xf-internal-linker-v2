#!/usr/bin/env python3
"""Pre-commit hook: Verify native C++ pipeline observability wiring.

Checks that the backend/extensions/ directory contains Perfetto
and GWP-ASan initialization, configured to the required hardware
profile tiers (Perfetto buffer_size_kb=4096, GWP-ASan SampleRate=5000,
MaxSimultaneousAllocations=16).
"""

from __future__ import annotations

import sys
import re
from pathlib import Path

EXTENSIONS_DIR = Path("backend/extensions")

# Expected hardware-aware configurations
EXPECTED_BUFFER_SIZE_KB = "4096"
EXPECTED_SAMPLE_RATE = "5000"
EXPECTED_MAX_SIMULTANEOUS_ALLOCS = "16"

def check_native_observability() -> int:
    if not EXTENSIONS_DIR.exists() or not EXTENSIONS_DIR.is_dir():
        print(f"Skipping check: {EXTENSIONS_DIR} does not exist.")
        return 0

    cpp_files = list(EXTENSIONS_DIR.rglob("*.cpp")) + list(EXTENSIONS_DIR.rglob("*.hpp")) + list(EXTENSIONS_DIR.rglob("*.h"))
    if not cpp_files:
        print(f"Skipping check: No C++ files found in {EXTENSIONS_DIR}.")
        return 0

    has_perfetto = False
    has_gwp_asan = False
    buffer_size_ok = False
    sample_rate_ok = False
    max_allocs_ok = False

    perfetto_regex = re.compile(r"perfetto\.h")
    gwp_asan_regex = re.compile(r"gwp_asan")
    buffer_size_regex = re.compile(rf"buffer_size_kb\s*=\s*{EXPECTED_BUFFER_SIZE_KB}")
    sample_rate_regex = re.compile(rf"SampleRate\s*=\s*{EXPECTED_SAMPLE_RATE}")
    max_allocs_regex = re.compile(rf"MaxSimultaneousAllocations\s*=\s*{EXPECTED_MAX_SIMULTANEOUS_ALLOCS}")

    for file_path in cpp_files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        
        if perfetto_regex.search(content):
            has_perfetto = True
        if gwp_asan_regex.search(content):
            has_gwp_asan = True
        if buffer_size_regex.search(content):
            buffer_size_ok = True
        if sample_rate_regex.search(content):
            sample_rate_ok = True
        if max_allocs_regex.search(content):
            max_allocs_ok = True

    errors = []
    if not has_perfetto:
        errors.append("Perfetto instrumentation missing (need '#include <perfetto.h>' or similar initialization).")
    if not has_gwp_asan:
        errors.append("GWP-ASan instrumentation missing (need gwp_asan integration).")
    if has_perfetto and not buffer_size_ok:
        errors.append(f"Perfetto buffer size must be configured to {EXPECTED_BUFFER_SIZE_KB} KB (low tier) using 'buffer_size_kb = {EXPECTED_BUFFER_SIZE_KB}'.")
    if has_gwp_asan and not sample_rate_ok:
        errors.append(f"GWP-ASan SampleRate must be configured to {EXPECTED_SAMPLE_RATE} (medium tier) using 'SampleRate = {EXPECTED_SAMPLE_RATE}'.")
    if has_gwp_asan and not max_allocs_ok:
        errors.append(f"GWP-ASan MaxSimultaneousAllocations must be configured to {EXPECTED_MAX_SIMULTANEOUS_ALLOCS} (medium tier) using 'MaxSimultaneousAllocations = {EXPECTED_MAX_SIMULTANEOUS_ALLOCS}'.")

    if errors:
        print("FAIL: Native C++ Observability Wiring Check Failed")
        for err in errors:
            print(f"  - {err}")
        print("\nUNBLOCK: Implement Perfetto and GWP-ASan in backend/extensions/ with correct configurations.")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(check_native_observability())
