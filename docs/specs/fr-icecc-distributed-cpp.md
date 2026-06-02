# FR: Distributed C++ Compilation via icecc

**Feature ID:** fr-icecc-distributed-cpp
**Author:** Claude (session 2026-05-27)
**Status:** implementing

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

---

## Problem

C++ compilation is the bottleneck step in the quality pipeline.
`cmake --build` inside the `compiled-tools` Docker container currently runs
with `--parallel 2`, using only two cores on the Windows machine.
Mint sits idle during this phase even though it is already online and
connected for the Go/Haskell quality steps.

Amdahl's Law (Amdahl 1967, doi:10.1145/1465482.1465560) shows that removing
the serial bottleneck in a mixed serial/parallel workload produces the largest
wall-clock improvements.  The C++ build is currently fully serial relative to
Mint; distributing it across both machines is the highest-leverage optimisation
available without changing the code itself.

---

## Solution

Use **icecc (Icecream)** — the open-source distributed GCC/Clang front-end —
to offload individual translation-unit compilations from the Windows Docker
container to the Mint compile daemon while keeping cmake as the build driver.

[SPEC CITED: feature=fr-icecc-distributed-cpp kind=technical_doc
 id=https://cmake.org/cmake/help/latest/variable/CMAKE_LANG_COMPILER_LAUNCHER.html
 verified_at=2026-05-27]

[SPEC CITED: feature=fr-icecc-distributed-cpp kind=academic_paper
 id=doi:10.1145/1465482.1465560 verified_at=2026-05-27]

---

## Architecture

```
Windows (Docker container: compiled-tools)
  icecc client installed (apt: icecc)
  ICECC_SCHEDULER = <Mint IP> (passed from orchestrator)
  cmake -DCMAKE_C_COMPILER_LAUNCHER=icecc
        -DCMAKE_CXX_COMPILER_LAUNCHER=icecc
        --parallel <total_cores>
  │
  │  each .cpp translation unit → preprocessed locally → sent to Mint
  ▼
Mint machine
  iceccd daemon   (port 10245, accepts compile jobs)
  icecc-scheduler (port 8765,  tracks available nodes)
  compiles received translation units, returns .o files
```

Both machines start simultaneously (existing orchestrator behaviour).
The scheduler on Mint tells the Windows icecc client which Mint cores are
free; Windows dispatches jobs there while local cores compile other files.

### Network path

Docker Desktop on Windows routes container traffic through the Windows host
via NAT.  The Windows host already has SSH access to Mint (used by the
orchestrator for the quality shard call).  The orchestrator resolves
`MINT_HOST` to its IP on the Windows host (where DNS is reliable) and passes
the IP directly to the container as `ICECC_SCHEDULER`, avoiding any DNS
lookup inside the container where resolution may fail.

Mint firewall must allow inbound TCP on ports **8765** (scheduler) and
**10245** (daemon) from the Windows host IP.  These are the icecc defaults
and are only exposed on the local network — they carry no secrets (only
preprocessed source and object files over an authenticated session when
`ICECC_VERSION` is set, optional for same-distro setups).

### Graceful fallback

`scripts/icecc_helper.sh` checks two conditions before enabling distributed
compilation:
1. `icecc` binary is present in `$PATH`.
2. `ICECC_SCHEDULER` environment variable is non-empty.

If either check fails the variable `ICECC_CMAKE_LAUNCHER_FLAGS` is left
empty and cmake builds locally — identical to the behaviour before this
change.  The C++ quality gate never fails because icecc is unavailable.

---

## Components changed

| File | Change |
|---|---|
| `tools/mutation/Dockerfile` | `apt-get install -y icecc` |
| `scripts/icecc_helper.sh` | New: sets `ICECC_CMAKE_LAUNCHER_FLAGS` |
| `scripts/run-cpp-tests.sh` | Source helper; pass launcher flags to cmake; raise `--parallel` |
| `scripts/run-cpp-quality.sh` | Pass `-e ICECC_SCHEDULER` into the Docker container |
| `scripts/run-mint-quality-shard.sh` | Start `iceccd` + `icecc-scheduler` before quality scripts |
| `scripts/run-scoped-static-quality.ps1` | Resolve Mint IP; set `ICECC_SCHEDULER`; export to cpp job |

---

## Expected speedup

With Mint providing, say, 8 remote cores alongside 12 local Windows cores,
cmake dispatches up to 20 parallel compile jobs instead of 2.
For a typical 60-file C++ workspace, wall-clock build time drops from
~60 s (2-parallel local) to ~10–12 s (20-parallel distributed) — a 5–6×
improvement on the compile step alone.  The full quality gate (which includes
ctest, mull, etc.) will not speed up by the same factor, but the dominant
bottleneck is removed.

---

## Constraints and limits

- Both machines must run the same GCC/Clang major version (guaranteed by the
  single `tools/mutation/Dockerfile` that both use).
- icecc does not distribute linking; only compilation (.cpp → .o) is
  distributed.  The final link step still runs locally in the container.
- `ICECC_VERSION` (toolchain tarball) is not needed when both nodes run the
  same OS and compiler version.  If versions diverge in future, set
  `ICECC_VERSION=auto` to force toolchain packaging.
- The icecc daemon on Mint should be stopped after the quality run to free
  resources.  `run-mint-quality-shard.sh` starts it with `--no-fork` inside
  a subshell so it terminates when the script exits.

---

## BDD

**Given** a commit that changes C++ files,
**When** the quality orchestrator runs and Mint is reachable,
**Then** cmake dispatches individual translation-unit compilations to Mint
  via icecc, reducing the total build time compared to local-only compilation,
  and all existing ctest tests still pass with the same results.

**Given** the Mint machine is unreachable or icecc is not installed,
**When** the quality orchestrator runs the C++ quality gate,
**Then** cmake falls back to local compilation and the gate still completes
  successfully without any error about icecc.
