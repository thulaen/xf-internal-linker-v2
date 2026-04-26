"""Update governance checkboxes across docs/specs/pick-*.md.

For picks shipped this session (Group A/B/C + Phase 6 + W1 + Phase 7),
flip the standard governance checkboxes that are now genuinely
satisfied:

- ``Helper module`` — every Phase 6 helper module landed.
- ``Test module`` — paired tests landed alongside.
- ``Benchmark module`` — Phase 7.1 ``test_bench_phase6_helpers.py`` covers
  the hot-path Phase 6 helpers + Group C retrievers.
- ``FEATURE-REQUESTS.md entry`` — FR-230 covers all 52 picks.
- ``AI-CONTEXT.md ledger`` — Phase 7.3 entry covers the session.
- ``Pipeline wired`` — true for picks whose W1 producer is real (not
  ``DeferredPickError``).

This script is idempotent — re-running on a checked-off file leaves
it unchanged. Each pick's "checkable" set is hard-coded so we don't
flip boxes for capabilities that aren't actually shipped (e.g. the
"Migration upserts rows" box stays unchecked because the
``Recommended preset`` migration that seeds the new keys hasn't
been written yet).

Usage::

    python backend/scripts/update_spec_checkboxes.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


SPEC_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "specs"


# Picks shipped this session. Maps the pick filename pattern to the
# set of label substrings whose checkbox should be flipped to [x].
# Keys are lower-case substrings of the spec filename (matched as
# 'pick-NN-' prefix).
SHIPPED_PICKS: dict[str, set[str]] = {
    "pick-07-": {"Helper module", "Test module", "Benchmark module"},
    "pick-13-": {"Helper module", "Test module", "Benchmark module"},
    "pick-14-": {"Helper module", "Test module", "Benchmark module"},
    "pick-15-": {"Helper module", "Test module", "Benchmark module"},
    "pick-17-": {"Helper module", "Test module", "Benchmark module"},
    "pick-18-": {
        "Helper module",
        "Test module",
        "Benchmark module",
        "Pipeline wired",
    },
    "pick-19-": {"Helper module", "Test module", "Benchmark module"},
    "pick-20-": {
        "Helper module",
        "Test module",
        "Benchmark module",
        "Pipeline wired",
    },
    "pick-21-": {"Helper module", "Test module", "Benchmark module"},
    "pick-22-": {"Helper module", "Test module", "Benchmark module"},
    "pick-23-": {
        "Helper module",
        "Test module",
        "Benchmark module",
        "Pipeline wired",
    },
    "pick-24-": {"Helper module", "Test module", "Benchmark module"},
    "pick-25-": {"Helper module", "Test module", "Benchmark module"},
    "pick-26-": {"Helper module", "Test module", "Benchmark module"},
    "pick-27-": {
        "Helper module",
        "Test module",
        "Benchmark module",
        "Pipeline wired",
    },
    "pick-28-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-29-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-30-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-31-": {
        "Helper module",
        "Test module",
        "Benchmark module",
        "Pipeline wired",
    },
    "pick-32-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-33-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-34-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-35-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-36-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-37-": {
        "Helper module",
        "Test module",
        "Benchmark module",
        "Pipeline wired",
    },
    "pick-38-": {
        "Helper module",
        "Test module",
        "Benchmark module",
        "Pipeline wired",
    },
    "pick-39-": {
        "Helper module",
        "Test module",
        "Benchmark module",
        "Pipeline wired",
    },
    "pick-40-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-41-": {"Helper module", "Test module"},
    "pick-42-": {"Helper module", "Test module"},
    "pick-43-": {"Helper module", "Test module"},
    "pick-44-": {"Helper module", "Test module"},
    "pick-45-": {"Helper module", "Test module"},
    "pick-46-": {"Helper module", "Test module"},
    "pick-47-": {"Helper module", "Test module"},
    "pick-48-": {"Helper module", "Test module"},
    "pick-49-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-50-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-51-": {"Helper module", "Test module", "Pipeline wired"},
    "pick-52-": {"Helper module", "Test module", "Pipeline wired"},
}

# These checkboxes should be flipped on EVERY shipped spec, not just
# ones with code changes — they're per-FR governance items that all
# 52 picks share.
GLOBAL_CHECKBOXES: set[str] = {
    "FEATURE-REQUESTS.md entry",
    "AI-CONTEXT.md ledger",
}

# Picks whose W1 scheduled-job entrypoint is REAL (not DeferredPickError).
# The matching label substring is "scheduled job registered" — the spec
# template wraps it as ``- [ ] \`<job_name>\` scheduled job registered (W1)``.
W1_WIRED_PICKS: set[str] = {
    "pick-18-",  # lda_topic_refresh
    "pick-20-",  # product_quantization_refit
    "pick-23-",  # kenlm_retrain
    "pick-33-",  # position_bias_ips_refit
    "pick-34-",  # cascade_click_em_re_estimate
    "pick-37-",  # node2vec_walks
    "pick-38-",  # bpr_refit
    "pick-39-",  # factorization_machines_refit
    "pick-50-",  # conformal_prediction_refresh
    "pick-51-",  # trustrank_auto_seeder
    "pick-52-",  # ACI alpha update (sub-job)
}
W1_LABEL = "scheduled job registered"


def _flip_box(line: str, label_set: set[str]) -> tuple[str, bool]:
    """Flip a single ``- [ ] <label>`` line if its label matches.

    Returns ``(new_line, did_change)``. Match is case-insensitive
    substring on the label portion (everything after the checkbox).
    Preserves the line's trailing newline (if any) so we don't
    collapse adjacent list items into a single line.
    """
    # Operate on the line *without* its trailing newline so the
    # ``$`` anchor is unambiguous; we restore the newline at the end.
    has_newline = line.endswith("\n")
    bare = line[:-1] if has_newline else line
    m = re.match(r"^(\s*-\s*)\[\s*\](\s*)(.*)$", bare)
    if not m:
        return line, False
    prefix, sep, body = m.group(1), m.group(2), m.group(3)
    # Specs often wrap filenames in backticks (e.g. ``- [ ] `FEATURE-REQUESTS.md` entry``).
    # Strip those before substring-matching so the label set doesn't have
    # to encode backtick variants.
    body_lower = body.lower().replace("`", "")
    for label in label_set:
        if label.lower() in body_lower:
            new_bare = f"{prefix}[x]{sep}{body}"
            return (new_bare + "\n" if has_newline else new_bare), True
    return line, False


def _update_spec(path: Path, pick_labels: set[str]) -> int:
    """Flip every matching checkbox in *path*. Returns the number flipped."""
    src = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    flipped = 0
    label_set = pick_labels | GLOBAL_CHECKBOXES
    for line in src:
        new_line, did = _flip_box(line, label_set)
        out.append(new_line)
        if did:
            flipped += 1
    if flipped:
        path.write_text("".join(out), encoding="utf-8")
    return flipped


def main() -> int:
    if not SPEC_DIR.is_dir():
        print(f"spec directory not found: {SPEC_DIR}", file=sys.stderr)
        return 1
    total_flipped = 0
    files_touched = 0
    for spec in sorted(SPEC_DIR.glob("pick-*.md")):
        prefix = (
            spec.name[: spec.name.find("-", 5) + 1]
            if spec.name.startswith("pick-")
            else ""
        )
        # Match "pick-NN-" exactly.
        m = re.match(r"^(pick-\d{2}-)", spec.name)
        if not m:
            continue
        prefix = m.group(1)
        pick_labels = SHIPPED_PICKS.get(prefix, set())
        # Add the "scheduled job registered" label for W1-wired picks.
        if prefix in W1_WIRED_PICKS:
            pick_labels = pick_labels | {W1_LABEL}
        if not pick_labels and not GLOBAL_CHECKBOXES:
            continue
        flipped = _update_spec(spec, pick_labels)
        if flipped:
            total_flipped += flipped
            files_touched += 1
            print(f"{spec.name}: flipped {flipped} checkbox(es)")
    print(f"\nTotal: {total_flipped} checkbox(es) across {files_touched} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
