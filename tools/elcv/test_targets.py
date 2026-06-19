#!/usr/bin/env python3
"""Tests for the ELCV target-lock logic. Run: python tools/elcv/test_targets.py"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import targets  # noqa: E402

HEAD = {
    "global_ceiling": 2000000000,
    "scopes": {
        "atlas": {"target": 1000000000, "loc_target": 2000000000, "locked": True},
        "ranklab": {"target": 28000000, "locked": True},
        "scratch": {"target": 100, "locked": False},
    },
}


def _staged(**overrides):
    import copy
    cfg = copy.deepcopy(HEAD)
    cfg.update(overrides.pop("_top", {}))
    for name, patch in overrides.items():
        cfg["scopes"].setdefault(name, {}).update(patch)
    return cfg


class LockTests(unittest.TestCase):
    def test_no_change_is_clean(self):
        self.assertEqual(targets.lock_violations(HEAD, HEAD), [])

    def test_lowering_locked_target_is_blocked(self):
        staged = _staged(atlas={"target": 5000000, "locked": True})
        self.assertTrue(any("atlas" in v for v in targets.lock_violations(HEAD, staged)))

    def test_raising_locked_target_is_allowed(self):
        staged = _staged(atlas={"target": 2000000000, "locked": True})
        self.assertEqual(targets.lock_violations(HEAD, staged), [])

    def test_removing_locked_scope_is_blocked(self):
        import copy
        staged = copy.deepcopy(HEAD)
        del staged["scopes"]["ranklab"]
        self.assertTrue(any("ranklab" in v for v in targets.lock_violations(HEAD, staged)))

    def test_removing_lock_flag_is_blocked(self):
        staged = _staged(ranklab={"target": 28000000, "locked": False})
        self.assertTrue(any("lock removed" in v for v in targets.lock_violations(HEAD, staged)))

    def test_lowering_global_ceiling_is_blocked(self):
        staged = _staged(_top={"global_ceiling": 5000000})
        self.assertTrue(any("global_ceiling" in v for v in targets.lock_violations(HEAD, staged)))

    def test_unlocked_scope_may_change(self):
        staged = _staged(scratch={"target": 1, "locked": False})
        self.assertEqual(targets.lock_violations(HEAD, staged), [])

    def test_lowering_locked_loc_target_is_blocked(self):
        staged = _staged(atlas={"loc_target": 5000000})
        self.assertTrue(any("loc_target" in v for v in targets.lock_violations(HEAD, staged)))

    def test_raising_locked_loc_target_is_allowed(self):
        staged = _staged(atlas={"loc_target": 3000000000})
        self.assertEqual(targets.lock_violations(HEAD, staged), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
