#!/usr/bin/env python3
"""In-container TWO-PHASE diff-scoped mutmut runner.

Invoked inside the ``backend-quality`` container by ``check-scoped-mutation.py``.
Whole-file mutation of a large legacy file times out (>30 min), so instead:

  Phase A — generate every mutant for the staged files using a NO-OP runner
            (``python -c ""`` always exits 0). This is fast: no real test runs,
            it just populates mutmut's cache so each mutant can be located.
  Locate  — for each mutant, read ``mutmut show`` and pin it to its source line;
            keep only mutants whose line is one THIS commit changed.
  Phase B — re-test ONLY those changed-line mutants with the REAL test runner.

Prints one ``LIVE <path>:<line>`` line per surviving changed-line mutant, then
``DONE``. ``NO_CHANGED_MUTANTS`` means there were no mutable changed lines.

Args (backend-relative paths, i.e. ``apps/...``):
  --paths    comma-separated source files to mutate
  --tests    space-joined test files for the real runner
  --changed  repeated ``path:line,line,...`` tokens (``path:ALL`` => whole file)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

_HUNK = re.compile(r"^@@ -(\d+)")

# Hard cap per Phase-B `mutmut run` call. A mutant whose test hangs (an unmocked
# network/DB call with no timeout) would otherwise block the whole gate forever;
# capping the call turns that into a clean LIVE-survivor failure instead.
_PHASE_B_CALL_TIMEOUT_SECONDS = 240

# Hard cap per Phase-A enumeration call. mutmut 2.x deadlocks its multiprocessing
# enumeration when handed MANY files in one `mutmut run` (observed: a 7-file batch
# wedges at 0% CPU forever, while any single file completes in minutes). So Phase A
# runs ONE file per call; this cap stops a single pathological file from wedging
# the gate and names it via PHASE_A_TIMEOUT instead of hanging.
_PHASE_A_FILE_TIMEOUT_SECONDS = 300


def _ids(status: str) -> list[str]:
    out = subprocess.run(
        ["mutmut", "result-ids", status],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    return out.split()


def _mutant_line(mutant_id: str) -> tuple[str, int] | None:
    """Return (path, original source line) for a mutant from `mutmut show`."""
    show = subprocess.run(
        ["mutmut", "show", mutant_id],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    lines = show.splitlines()
    path: str | None = None
    start: int | None = None
    body_start = 0
    for i, ln in enumerate(lines):
        if ln.startswith("--- "):
            path = ln[4:].strip()
        m = _HUNK.match(ln)
        if m:
            start = int(m.group(1))
            body_start = i + 1
            break
    if path is None or start is None:
        return None
    cur = start
    for ln in lines[body_start:]:
        if ln.startswith("@@"):
            break
        if ln.startswith("-"):
            return (path, cur)
        if ln.startswith("+"):
            continue
        cur += 1
    return (path, start)


def _parse_changed(tokens: list[str]) -> dict[str, set[int] | str]:
    changed: dict[str, set[int] | str] = {}
    for tok in tokens:
        path, _, lines = tok.partition(":")
        if lines.strip() == "ALL":
            changed[path] = "ALL"
        else:
            changed[path] = {int(x) for x in lines.split(",") if x.strip()}
    return changed


def _on_changed(loc: tuple[str, int], changed: dict[str, set[int] | str]) -> bool:
    path, line = loc
    sel = changed.get(path)
    if sel is None:
        return False
    if sel == "ALL":
        return True
    return line in sel


def _runner_for(tests: list[str]) -> str:
    """The real pytest runner SCOPED to one source file's own tests.

    Per-file scoping is the difference between a feasible gate and a timeout:
    mutmut re-runs the runner once per mutant, so feeding it the flat UNION of
    every staged file's tests (including slow DB-backed suites) makes each
    mutant cost the whole suite. A command file's mutants only ever die to that
    command's own (fast) test, so we run only those.

    --reuse-db: pytest-django creates the test DB once and reuses it for every
    mutant iteration. Without it the DB is dropped + recreated per run; a
    lingering connection makes the drop fail ("database is being accessed by
    other users"), the DB-backed tests then ERROR, `pytest -x` stops early, and
    later mutants are reported as FALSE survivors.
    """
    return (
        "python -m pytest -x -p no:randomly --reuse-db --override-ini=addopts= "
        + " ".join(tests)
    )


def _parse_tests_map(
    tokens: list[str], union: str, paths: str
) -> dict[str, list[str]]:
    """`rel::t1,t2` tokens -> {source_rel: [test_rel, ...]}.

    Any --paths source absent from the map falls back to the flat --tests union
    (keeps older callers that pass only --tests working)."""
    mapping: dict[str, list[str]] = {}
    for tok in tokens:
        rel, sep, tests = tok.partition("::")
        parsed = [t for t in tests.split(",") if t]
        # Only record a NON-EMPTY scoped list. A file with no convention test
        # (empty list) falls through to the union below, so its mutants are
        # still tested by SOMETHING — never `_runner_for([])`, which would run
        # pytest with no target and either sweep the whole suite or exit 5.
        if sep and parsed:
            mapping[rel] = parsed
    union_tests = union.split()
    for src in paths.split(","):
        mapping.setdefault(src, union_tests)
    return mapping


def _phase_b_plan(
    keep: list[str],
    located: dict[str, tuple[str, int]],
    by_file_all: dict[str, list[str]],
    tests_map: dict[str, list[str]],
) -> list[tuple[str, str]]:
    """Pair each Phase-B mutmut call with ONE positional and ITS file's runner.

    mutmut 2.x `mutmut run` accepts EXACTLY ONE argument — a single mutant id
    OR a file path. We hand it a whole-FILE path when every enumerated mutant
    of that file is a changed-line mutant (a brand-new / fully-changed file):
    `mutmut run <file>` re-tests them all under ONE shared baseline. For a
    partially-changed file we fall back to the individual kept ids. Either way
    the runner is scoped to that file's own tests (see `_runner_for`). The
    order is files-then-ids, grouped per file, deterministic for a given input.
    """
    by_file_keep: dict[str, list[str]] = {}
    for mid in keep:
        by_file_keep.setdefault(located[mid][0], []).append(mid)
    plan: list[tuple[str, str]] = []
    for fpath, kept in by_file_keep.items():
        runner = _runner_for(tests_map.get(fpath, []))
        if len(kept) == len(by_file_all.get(fpath, ())):
            plan.append((fpath, runner))
        else:
            plan.extend((mid, runner) for mid in kept)
    return plan


def _phase_b(plan: list[tuple[str, str]]) -> None:
    """Run each (positional, runner) pair as its own mutmut invocation.

    mutmut 2.x `mutmut run` takes ONE positional ("either an integer that is
    the mutation id or a path to a file to mutate"). Passing several at once
    (``mutmut run 1 2 3`` or ``mutmut run 1,2,3``) exits 2 WITHOUT testing
    anything, so every unit silently keeps its Phase-A no-op 'survived' verdict
    and is reported as a FALSE survivor — the latent bug that bit only when
    >=2 changed-line mutants existed. One positional per invocation.
    """
    for positional, runner in plan:
        try:
            subprocess.run(
                ["mutmut", "run", positional, "--runner", runner],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=_PHASE_B_CALL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            # A mutant whose test HANGS (e.g. an unmocked network/DB call with no
            # timeout) would otherwise block the gate forever. Cap each mutmut
            # call; on timeout the mutant keeps its Phase-A 'survived' verdict and
            # is reported LIVE below, so the gate fails CLEANLY instead of hanging.
            print(f"PHASE_B_TIMEOUT {positional}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", required=True)
    ap.add_argument("--tests", required=True)
    ap.add_argument("--tests-map", nargs="*", default=[])
    ap.add_argument("--changed", nargs="*", default=[])
    args = ap.parse_args()
    changed = _parse_changed(args.changed)
    # Per-file test scoping: each source file's mutants are re-tested against
    # ONLY that file's own tests (see `_runner_for`), not the flat union — that
    # is what keeps the gate under its time budget when several files are staged.
    tests_map = _parse_tests_map(args.tests_map, args.tests, args.paths)

    # Determinism: a stale `.mutmut-cache` left by a PRIOR run on this bind-
    # mounted tree makes mutmut REUSE old verdicts and silently report a false
    # pass (observed: Windows kept a cache that marked changed-line mutants
    # "killed" while a fresh run on another machine found 4 real survivors —
    # K8S.26 §14). Clear it so every run starts from a clean slate.
    try:
        os.remove(".mutmut-cache")
    except OSError:
        pass

    # Phase A: generate mutants fast (no-op runner => every mutant survives).
    # IMPORTANT: do NOT pass --use-coverage here. coverage.py attributes a
    # multi-line literal (dict / list / call) to its OPENING line only, so
    # mutants on the inner lines look "uncovered"; with --use-coverage mutmut
    # then skips re-testing them and they are reported as FALSE survivors on
    # ANY changed multi-line literal. Phase A already scopes to changed lines
    # and Phase B re-tests each kept mutant with the real runner, so coverage
    # gating buys nothing here and only manufactures false positives.
    # Run ONE file per call: mutmut 2.x deadlocks when enumerating many files in a
    # single invocation, but each file completes alone. The runs accumulate every
    # file's mutants into the shared .mutmut-cache, so the locate step below still
    # sees them all. A per-file timeout names a pathological file rather than wedge.
    for _one_path in (p.strip() for p in args.paths.split(",") if p.strip()):
        try:
            subprocess.run(
                ["mutmut", "run", "--paths-to-mutate", _one_path, "--runner",
                 'python -c ""'],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=_PHASE_A_FILE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            print(f"PHASE_A_TIMEOUT {_one_path}")

    # Sanity guard: the no-op runner makes EVERY generated mutant "survive", so
    # an empty survived-set means Phase A produced ZERO mutants. For real source
    # with changed lines that signals mutmut could not enumerate (a corrupt /
    # stale cache or a tool error), NOT a clean result. Emit a non-DONE sentinel
    # so the host treats it as "could not run" (hard fail) instead of letting
    # the empty keep-set fall through to a FALSE 0-survivor pass.
    all_ids = _ids("survived")
    if not all_ids:
        print("PHASE_A_NO_MUTANTS")
        return 1

    # Locate every enumerated mutant; group by file and keep changed-line ones.
    located: dict[str, tuple[str, int]] = {}
    by_file_all: dict[str, list[str]] = {}
    for mid in all_ids:
        loc = _mutant_line(mid)
        if loc is None:
            continue
        located[mid] = loc
        by_file_all.setdefault(loc[0], []).append(mid)
    keep = [mid for mid, loc in located.items() if _on_changed(loc, changed)]

    if not keep:
        print("NO_CHANGED_MUTANTS")
        return 0

    # Phase B: re-test ONLY the changed-line mutants with the real runner,
    # handing mutmut ONE positional per call (a whole-file path when every
    # mutant of a file is a changed-line mutant — one shared baseline — else
    # the individual ids), each scoped to its own file's tests.
    _phase_b(_phase_b_plan(keep, located, by_file_all, tests_map))

    survived = set(_ids("survived"))
    for mid in keep:
        if mid in survived:
            loc = _mutant_line(mid)
            if loc is not None:
                print(f"LIVE {loc[0]}:{loc[1]} (mutant {mid})")
                show = subprocess.run(
                    ["mutmut", "show", mid], capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                ).stdout
                for dl in show.splitlines():
                    if dl.startswith(("+", "-", "@@")):
                        print("  | " + dl)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
