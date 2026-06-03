# FR — run the scoped mutation gate on the remote 14-core (6 P-cores + 8 E-cores) / 20-thread "Dell" over SSH

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-06-30]
[SPEC CITED: feature=dell-mutation-runner kind=technical_doc id=mutmut-docs verified_at=2026-06-01]
[SPEC CITED: feature=dell-mutation-runner kind=technical_doc id=pytest-django-reuse-db verified_at=2026-06-01]
[SPEC CITED: feature=dell-mutation-runner kind=technical_doc id=openssh-manual verified_at=2026-06-01]
[SPEC CITED: feature=weighted-turbo-split kind=academic_paper id=balinski-young-fair-representation-1982 verified_at=2026-06-01]

## Problem

The repo has a hard commit gate called "scoped mutation". In plain English: it makes
tiny edits to the lines you changed (turn a `+` into a `-`, a `True` into a `False`),
re-runs the tests, and if the tests still pass it means those lines are not really
tested — the commit is blocked. This check is slow.

Today it runs on the everyday Windows laptop (nicknamed the "MSI"), which has only
**8 CPU cores**. Mutation testing is CPU-heavy, so on 8 cores the gate can take many
minutes. Meanwhile there is a second, faster Windows machine on the same home network —
nicknamed the **"Dell"** (an Intel **i5-13500T**: **14 cores (6 Performance-cores + 8
Efficient-cores), 20 threads** and ~15.7 GB of RAM) that normally sits
idle. The goal of this feature is to let the slow mutation gate run on the Dell instead,
so commits clear faster, without changing the verdict it returns.

This is **opt-in**. You turn it on by setting one environment variable:
`XF_MUTATION_HOST=dell`. When that variable is not set, nothing changes and the gate runs
locally exactly as before.

## Sources of truth

- **mutmut documentation** (`mutmut-docs`) — the mutation-testing tool this gate drives
  (`mutmut run`, `mutmut result-ids`, `mutmut show`). Defines how mutants are generated,
  located, and reported, and why this repo pins mutmut to the 2.x line.
- **pytest-django `--reuse-db`** (`pytest-django-reuse-db`) — the test-runner flag that
  creates the throwaway test database once and reuses it across runs instead of dropping
  and recreating it every time. This is the root-cause fix for the flakiness described
  below.
- **OpenSSH manual** (`openssh-manual`) — the secure remote-shell tooling (`ssh`,
  `BatchMode=yes` for non-interactive connections, key-based authentication) used to reach
  the Dell and pipe the source snapshot to it.

## Behaviour (Given / When / Then)

- **Given** the environment variable `XF_MUTATION_HOST=dell` is set,
  **When** the scoped-mutation gate runs (on commit, or when invoked by hand),
  **Then** the current working-tree source is packed into a tar archive and streamed to
  the Dell over SSH, mutmut runs inside the Dell's `backend-quality` container against that
  exact snapshot, and the gate returns the **same survivor verdict** it would have returned
  locally — a surviving mutant on a changed line still hard-blocks the commit, and a clean
  run still prints `[SCOPED MUTATION: ...]`.

## Design

The Dell path lives in `.githooks/check-scoped-mutation.py`. When
`XF_MUTATION_HOST=dell` (compared case-insensitively), `_run_mutmut` delegates to
`_run_mutmut_on_dell` instead of the local Docker run. The remote run has four moving
parts.

### 1. Source snapshot sync (`_sync_source_to_dell`)

Mutation must run against the **exact** source on this machine, not a stale or partial
copy. A partial file copy silently produces wrong results (false survivors), which is the
historical reason remote mutation was kept off. So before every remote run the helper
takes a fresh snapshot: it tars the `backend` tree plus the `.githooks` helpers (skipping
junk like `__pycache__`, `*.pyc`, `*.so`, build folders, caches, and `backend/reports`)
and pipes that archive straight into `ssh ... "cd <dell repo> && tar -xf -"`, which
unpacks it on the Dell.

This is done with Python's `subprocess.Popen` piping `tar` into `ssh`, **not** by calling
a bash script. That matters on Windows: a shell-script approach would resolve `bash` to
WSL (Windows Subsystem for Linux), which may not be installed. Doing the pipe in
Python keeps the sync working with only `tar` and `ssh` on the PATH. (A bash twin,
`.githooks/_sync_to_dell.sh`, exists for POSIX machines, but the Python path is what the
gate actually uses.) The Dell's copy is disposable — it is re-synced every run and mutmut
edits it in place — so unlike the local run there is no snapshot/restore of host files.

### 2. `--no-deps` — skip redis

The remote command runs `docker compose run --rm --no-deps -T -w /repo/backend
backend-quality ...`. The `--no-deps` flag tells Docker Compose **not** to start the
service's dependencies. The mutation tests use Django's in-memory cache (`LocMemCache`),
so redis is never needed; skipping it makes the run start faster and avoids booting a
container the tests do not touch.

### 3. Empty / clean `DOCKER_CONFIG` — dodge the SSH credential-helper failure

The remote command is prefixed with `set DOCKER_CONFIG=<clean dir>`. On Windows, Docker's
default config can be wired to a credential helper that fails when invoked over an SSH
session, which would crash the `docker compose run` before any test runs. Pointing
`DOCKER_CONFIG` at a clean, empty directory (no credential helper configured) sidesteps
that failure entirely. Arguments are passed through `_dell_quote`, which double-quotes any
argument containing spaces so `cmd.exe` and Docker keep them whole.

### 4. `--reuse-db` — the root-cause fix for false survivors

This is the most important correctness fix and lives in `.githooks/_mutmut_diff_scope.py`,
in both the coverage command and the real mutation runner command. The flag is
`--reuse-db`.

Without it, pytest-django **drops and recreates** the throwaway test database on every
mutmut iteration. If a database connection from the previous iteration is still open, the
drop fails with `database is being accessed by other users`. The database-backed tests
then ERROR, and because the runner uses `pytest -x` (stop on first failure), pytest stops
**before** reaching a later test that would have killed a mutant in a later file. The
result is a **false survivor** — the gate blocks a commit over a line that is actually
tested. This was observed specifically on management-command "glue" code.

`--reuse-db` fixes the root cause: the test database is created **once** and reused for
every mutmut iteration, never dropped mid-run, so the teardown race that produced the
false survivors cannot happen. The verdict the Dell returns is therefore both faster and
more correct than the flaky local behaviour it replaces.

## One-time Dell setup

These steps are done once on the Dell so the remote runner has everything it needs:

- **SSH host alias.** An SSH config entry named `dell` pointing at `192.168.0.163`, user
  `PC`, using the private key `~/.ssh/dell_xf`. `BatchMode=yes` is used so the connection
  never waits for a password prompt — key auth must already work.
- **Container images loaded.** The `xf-linker-backend-quality` image and the pgvector
  Postgres image are copied to the Dell with the `docker save | docker load` pattern (save
  the image to a tar stream on the MSI, pipe it over SSH, load it on the Dell). This avoids
  re-pulling or rebuilding on the Dell.
- **Postgres running.** `docker compose up -d postgres` on the Dell so the test database
  has a server to talk to before any mutation run starts.

Optional overrides (all read from environment variables, with sensible defaults):
`DELL_HOST` (default `dell`), `DELL_REPO_PATH` (default
`C:\Users\PC\xf-internal-linker-v2`), and `DELL_DOCKER_CONFIG` (default
`C:\Users\PC\.docker-mut`).

## How to enable / verify

Run the gate by hand with the variable set:

```
XF_MUTATION_HOST=dell python .githooks/check-scoped-mutation.py
```

A clean run prints the usual `[SCOPED MUTATION: diff-mode, 0 surviving mutants on changed
lines, files=N]` line. A real surviving mutant on a changed line prints the `LIVE
<path>:<line> (mutant ...)` detail and exits non-zero, exactly as the local run does.

## Why it is safe and why it is not the default

- **Safe:** mutation only gives a correct answer when it runs against the exact staged
  source. The tar source-snapshot sync provides precisely that snapshot before every run,
  and the Dell's copy is disposable and re-synced each time, so there is no risk of a stale
  or partial checkout silently changing the verdict.
- **Not default (yet):** remote mutation has historically produced wrong results when a
  copy was partial, so this path stays **opt-in** behind `XF_MUTATION_HOST=dell` until it
  has been proven correct across more commits. Until then the local Windows run remains the
  default, and turning the Dell on is a deliberate, reversible choice.

## Weighted three-machine turbo split

The single hard-gate (`check-scoped-mutation.py`) above runs on ONE machine at a time.
Separately, the **turbo coordinator** (`scripts/turbo_mutation.py`, activated by
`XF_TURBO_MUTATION=1`) fans the slow compiled-language mutation work (C++, Go, Rust,
Haskell) out across **all three machines in parallel by weight**, so the wall-clock time
drops. This section is the source of truth for that weighted split.

### Sources of truth (this section)

- **Balinski & Young, *Fair Representation* (1982, ISBN 0-300-02724-9)** — the
  largest-remainder (Hamilton) apportionment method. We use it to split a whole number of
  test targets across machines by weight so the per-machine counts always sum **exactly**
  to the number of targets, with no target dropped or double-assigned.
- The mutmt / pytest-django / OpenSSH sources above still apply to the SSH transport.

### The three machines and their weights

The weights live in `config/mutation-routing.json` under an ordered `machines` array.
Each entry is a plain-English record:

```
"machines": [
  { "name": "dell",    "transport": "docker_context", "context": "dell", "weight": 0.70, "max_weight": 0.85 },
  { "name": "windows", "transport": "docker_local",                      "weight": 0.20, "max_weight": 1.0 },
  { "name": "mint",    "transport": "docker_context", "context": "mint", "weight": 0.10, "max_weight": 1.0 }
]
```

- **name** — a stable label used as the report-file suffix and the log tag.
- **transport** — one of three literal strings: `docker_local` (run `docker compose exec`
  on this box = the everyday MSI/Windows laptop), `docker_context` (run
  `docker --context <context> compose exec` = the Dell and the Mint helper, each addressed by
  its own `context`), or `ssh` (tar-sync the source to the box then `ssh <host> ... docker
  compose run --rm --no-deps ...` — the legacy single-Dell transport, kept for the opt-in
  `XF_MUTATION_HOST=dell` path).
- **weight** — the machine's relative share. The three need **not** pre-sum to 1.0; the
  selector renormalises whatever machines actually answer.
- **max_weight** — a **ceiling** applied before renormalising. The Dell is capped at `0.85`,
  so 85 % is a *maximum*, never an exact target. The other two have `1.0` (no cap). The Dell
  carries the heaviest base share (`0.70`) because it is the fastest box — an Intel i5-13500T
  with 14 cores (6 P-cores + 8 E-cores) / 20 threads.
- **context** is required only for `docker_context` (the Dell uses context `dell`, the Mint
  helper uses context `mint`); **ssh_host** only for the legacy `ssh` transport.

The legacy `split{ local_pct, remote_pct, remote_context }` block is **kept** alongside the
new `machines` array. The loader prefers `machines` when present and falls back to the old
block otherwise, so a config in today's mint-only shape keeps working as the same 65/35
two-way split with zero migration.

### Hamilton (largest-remainder) target split

`_partition_weighted(items, machines)` splits a list of targets (the C++ binaries, or a
one-slot-per-machine placeholder for the workspace-wide Go/Rust/Haskell tools) like this:

1. For each machine, `raw = count * share`, `floor = int(raw)`, `remainder = raw - floor`.
2. `leftover = count - sum(floors)` (always 0..number-of-machines-1). Sort machines by
   remainder **descending**, ties broken by input order (deterministic), and hand one extra
   target to the first `leftover` machines.
3. Slice the targets into contiguous, disjoint blocks by the final per-machine counts.

The counts therefore sum **exactly** to the number of targets. Worked example: 9 C++
binaries at shares 0.70 / 0.20 / 0.10 → raw 6.3 / 1.8 / 0.9 → floors 6 / 1 / 0 (sum 7),
leftover 2 goes to the two largest remainders (mint 0.9, windows 0.8) → final
**dell 6 / windows 2 / mint 1 = 9**. With fewer targets than machines (1 target across 3),
the single target lands on the largest-share machine (dell) and the other two get empty
slices and are skipped at dispatch.

### Fail-open: a powered-off machine never blocks

The Dell (or any machine) can be switched off. All reachability + ceiling + renormalise
logic lives in one place, `_select_machines(cfg, probe)`:

1. **Probe each machine once, up front.** The probe is bounded so a dead box never hangs:
   `docker info` (15 s) for the docker transports, `ssh -o BatchMode=yes -o ConnectTimeout=8
   <host> true` (10 s) for the SSH transport. It never raises.
2. **Drop every unreachable machine before any work is partitioned.** This is fail-**open**:
   a dead box's targets are reassigned to the machines that answer, never sent to a box that
   cannot run them.
3. **Clamp each survivor to its `max_weight`** (Dell to 0.85), then **renormalise** the
   survivors to sum to 1.0, then **re-apply the ceiling** in a short bounded loop so the cap
   holds even after renormalisation pushes an uncapped machine up.
4. If only one machine answers it gets share 1.0; if **none** answer, fall back to a single
   synthetic Windows/`docker_local` machine at share 1.0 so the run still happens locally.

Worked redistribution examples (all asserted by unit tests in
`scripts/test_turbo_mutation.py`):

| Reachable | Resulting shares |
|---|---|
| dell + windows + mint | dell 0.70, windows 0.20, mint 0.10 |
| windows + mint (Dell OFF) | windows 0.667, mint 0.333 (Dell's 70 % redistributed) |
| dell + windows (Mint OFF) | dell **0.78**, windows 0.22 — 0.78 < the 0.85 ceiling, so NO clamp |
| windows only (Dell + Mint OFF) | windows 1.0 — identical to today's local-only run |

### Why SSH-tar for the Dell, not a new docker context

A `docker context create dell --docker host=ssh://...` would route Docker over SSH and
re-trigger the Windows credential-helper crash that §3 above works around with a clean
`DOCKER_CONFIG`, and that env cannot be injected into a context-over-SSH shell. So the turbo
SSH branch reuses the **proven** explicit path: tar-sync the source first
(`_sync_source_to_dell`, imported from `check-scoped-mutation.py` so there is one copy of
the logic), then `ssh <host> "set DOCKER_CONFIG=<clean dir> && docker compose run --rm
--no-deps -T <container> bash -lc <cmd>"`. The ephemeral `compose run --rm` needs no
long-lived container on the Dell.

### Python and TypeScript stay Windows-only

The per-language `split: true|false` flags are unchanged. `python` and `typescript` keep
`split: false`: their containers exist only on Windows, so fanning them out would copy a
partial source tree to another box and report **false survivors**. A `split: false` language
always collapses to the single `docker_local` machine regardless of the `machines` array.

### One-time setup to enrol the Dell in the turbo split

The operator runs these by hand once (the turbo coordinator never runs live Docker/SSH
setup itself):

1. Confirm the SSH alias `dell` in `~/.ssh/config` works:
   `ssh -o BatchMode=yes -o ConnectTimeout=8 dell true`
2. Load the compiled-language tools image onto the Dell (for C++/Go/Rust/Haskell):
   `docker save xf-linker-compiled-tools:latest | ssh dell "docker load"`
3. (If missing) load the Python quality image too:
   `docker save xf-linker-backend-quality:latest | ssh dell "docker load"`
4. Make a clean Docker-config dir so the SSH credential helper does not crash:
   `ssh dell "mkdir C:\Users\PC\.docker-mut"`
5. Bring up Postgres for the throwaway test DB:
   `ssh dell "cd C:\Users\PC\xf-internal-linker-v2 && docker compose up -d postgres"`

Environment overrides (defaults shown): `DELL_HOST=dell`,
`DELL_REPO_PATH=C:\Users\PC\xf-internal-linker-v2`,
`DELL_DOCKER_CONFIG=C:\Users\PC\.docker-mut`. No `compose up -d compiled-tools` is needed
because the SSH transport uses ephemeral `compose run --rm`, not `compose exec`.

> Note: a `docker context create dell ...` is deliberately **not** used (see "Why SSH-tar"
> above). The one-time enrolment is the five steps listed here, not a context creation.

## Per-commit gate three-machine weighted split (XF_MUTATION_SPLIT=1, conservative local-recover model)

The everyday **per-commit** scoped-mutation gate above ran on **one** machine and took
about 35 minutes on the 8-core MSI for a large multi-file commit. This section adds an
opt-in mode that fans the SAME gate across all three machines in parallel by weight, the
same way the turbo SWEEP already does — but with a stricter correctness model because this
is a hard gate hit on every commit. It is turned on with the environment variable
`XF_MUTATION_SPLIT=1`; with the variable unset the gate behaves exactly as before.

This split reuses the *same* selector and partitioner the turbo sweep uses. They were
moved into a new tiny module, `scripts/machine_routing.py`
(`_select_machines`, `_partition_weighted`, `_renormalise_with_ceilings`,
`_local_machine`, `_dispatch_to_machines`), which has zero Django imports and does not
import either caller, so both `scripts/turbo_mutation.py` and
`.githooks/check-scoped-mutation.py` load that one copy of the weighting math. Cross-reference
the "Weighted three-machine turbo split" section above — the apportionment is identical and
is still covered by Balinski & Young (Hamilton / largest-remainder), so no new citation is
introduced.

### What is distributed

The unit of work is the **staged source files** (already capped at 15 files). Each file is a
self-contained work item: it carries its own changed-line token (`path:line,line` or
`path:ALL`) and its own naming-convention test file, so a file's mutants can only die to its
own test on whichever machine owns it. `_partition_weighted` hands Dell about 70 % of the
files (capped at 85 %), Windows about 20 %, and Mint about 10 %, as **disjoint** contiguous
slices that sum to the file count exactly once — so total work across the fleet is the staged
file set exactly once, never doubled. Cost is approximated by file count, not CPU-time, so a
1-2 file commit lands entirely on one machine or collapses to local; the win is on the large
multi-file commits that caused the 35-minute pain.

### The manifest-verified snapshot handshake (closes the "no content-hash verification" gap)

Every REMOTE must PROVE it holds a full, exact copy of the staged source before its result is
trusted. An unverified remote is treated as poison: its files are re-run locally, never
trusted. Three layers, strongest last:

1. **Host manifest.** Before dispatch the host computes `sha256` of each `backend/<rel>` file
   in a remote's slice (`_host_hashes`).
2. **Full tar push.** A single shared tar producer (`_tar_producer`, identical exclude list
   for Dell and Mint) is piped into the remote's extractor. Dell extracts onto its own
   filesystem over SSH (`_sync_source_to_dell`). Mint receives a **new, identical** full push
   (`_sync_source_to_mint`) into an ephemeral `docker --context mint compose run --rm
   --no-deps` container — **never** a plain `compose exec` against Mint's stale bind-mounted
   checkout, which is the exact partial-source condition that originally banned Mint.
3. **Remote manifest handshake.** After the tar lands the host asks the remote to recompute
   `sha256sum` of the same slice paths inside its synced copy (`_verify_snapshot`). The slice
   is trusted only if **every** file's remote hash equals the host hash. A mismatch, a missing
   file, or a non-zero remote exit means the snapshot is NOT verified, so the slice is re-run
   locally.

As a backstop, the helper's `PHASE_A_NO_MUTANTS` sentinel still fires on every machine: an
empty enumerated-mutant set means stale/missing source, which fails completion and routes to
the local re-run too. The manifest handshake is an additional layer on top of the eight
existing false-pass guards, never a replacement.

> Honest limitation (recorded as future work, not a silent gap): a `compose run --rm`
> container's filesystem is discarded when it exits, so the Mint push, the manifest
> handshake, and the helper run must all observe the same synced copy. The implementation
> keeps `_sync_source_to_mint`, `_verify_snapshot`, and the helper run as separately-testable
> units composed in strict order (sync → verify → run); making the synced copy persist across
> those three `compose run` invocations on Mint (a named volume or a host-path extract) is the
> one piece that needs live-Mint validation before Mint is trusted in production. Until that
> is validated on the live Mint, leave `XF_MUTATION_SPLIT` unset, or a reachable-but-broken
> Mint simply degrades to a correct local re-run.

### Merge rule — union of confirmed survivors

Because the partition is a disjoint cover, each file has exactly one final judge, so the
merged survivor set is a plain **union** of every completing machine's surviving mutants
(`_merge_machine_results`) — no de-duplication and no "survived on A but died on B"
reconciliation is possible. A mutant is a confirmed real survivor only if it appears as a
`LIVE` line from the machine that finally owned that file AND that machine's run completed
(`_parse_live` saw `DONE` or `NO_CHANGED_MUTANTS`) AND, for a remote, its snapshot verified.

### Two fallback axes, never conflated

- **Powered-off boxes → fail-OPEN at probe time.** `_select_machines` probes each machine
  once with bounded budgets, drops every unreachable box BEFORE any file is assigned, clamps
  Dell to its 0.85 ceiling, and renormalises survivors to 1.0 (falling back to a single local
  Windows machine if nothing answers). A switched-off box never owns a file and never blocks
  the commit. Same redistribution table as the turbo section.
- **Reachable-but-broken boxes → fail-CLOSED then local-recover.** A box that answered the
  probe but whose run breaks after dispatch (sync failure, manifest mismatch, timeout, or a
  non-completing helper) is NOT redistributed mid-run and NOT passed silently — its files are
  re-run on the always-trusted local Windows runner (`_local_run`), whose verdict becomes
  final for those files. Only if the LOCAL re-run *also* cannot complete does the gate
  hard-fail. So a transient remote hiccup never blocks a good commit, and a broken remote can
  never produce a false pass.

### How a powered-off or stale-source machine can never cause a false pass

- **Powered off:** dropped at probe time, owns zero files, contributes nothing — its share is
  redistributed to live machines (or collapses to local). It cannot return a verdict at all.
- **Stale / partial source:** caught three ways — the host-vs-remote `sha256` manifest
  mismatch, the helper's `PHASE_A_NO_MUTANTS` zero-mutant sentinel (non-completion), and the
  `_parse_live` completion gate. Any of the three marks the slice untrusted, and an untrusted
  slice is re-judged on the local runner, never treated as zero survivors.

### Backward compatibility

`_run_mutmut` dispatches in an explicit order so the two existing modes are byte-for-byte
unchanged: (1) `XF_MUTATION_HOST=dell` → the existing single-Dell `_run_mutmut_on_dell`
(checked FIRST, so the legacy flag wins even if `XF_MUTATION_SPLIT=1` is also set);
(2) `XF_MUTATION_SPLIT=1` → the new `_run_mutmut_split`; (3) neither → today's single local
`backend-quality` run with snapshot/restore. When the split path runs but only Windows is
reachable, `_select_machines` collapses to the single local machine and the result is
identical to today's single-machine run. No config change is needed — the gate reads the same
`machines` array in `config/mutation-routing.json` that the turbo sweep reads.

### Mint prerequisite

Like the Dell, Mint must have Postgres up and the `backend-quality` image present for the
slice's tests to run; a Mint that lacks a DB trips Phase B errors → non-completion → safe
local re-run (which has a DB), so it degrades to a correct verdict rather than a wrong one.
