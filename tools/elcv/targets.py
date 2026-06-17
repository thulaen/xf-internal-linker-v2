#!/usr/bin/env python3
"""ELCV target-lock logic (pure + testable).

A scope marked "locked": true in elcv-scopes.json may be RAISED but never lowered,
removed, or unlocked, unless the config carries a top-level "unlock": "<reason>". The
global ceiling is likewise lock-only-up. This is what makes 1B (and 28M / 5M / 2B) a firm,
agent-proof commitment — no silent down-scoping (the Codex 28M->5M incident).

The git plumbing lives in .githooks/check-elcv-targets.py; this module is the pure
comparison so it can be unit-tested without git.
"""
from __future__ import annotations


def lock_violations(head: dict, staged: dict) -> list[str]:
    """Return reasons the *staged* config illegally erodes locked targets vs *head*.

    An empty list means the change is allowed (raises, additions, edits to unlocked
    scopes, or a present top-level "unlock" override are all fine — the override is
    checked by the caller, not here)."""
    out: list[str] = []

    head_ceiling = head.get("global_ceiling")
    if head_ceiling and staged.get("global_ceiling", 0) < head_ceiling:
        out.append(f"global_ceiling lowered {head_ceiling} -> {staged.get('global_ceiling')}")

    head_scopes = head.get("scopes", {})
    staged_scopes = staged.get("scopes", {})
    for name, definition in head_scopes.items():
        if not definition.get("locked"):
            continue  # unlocked scopes may change freely
        if name not in staged_scopes:
            out.append(f"locked scope '{name}' removed")
            continue
        new = staged_scopes[name]
        if new.get("target", 0) < definition.get("target", 0):
            out.append(
                f"locked scope '{name}' target lowered {definition['target']} -> {new.get('target')}")
        if not new.get("locked", False):
            out.append(f"locked scope '{name}' had its lock removed")
    return out
