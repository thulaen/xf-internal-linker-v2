"""Alias: run the full shard-planner test suite from its canonical location.

The guard requires a test file whose stem matches the production file
(plan-scoped-quality-shards.py → test_plan-scoped-quality-shards.py).
The actual tests live in scripts/tests/test_shard_planner.py.
"""
from scripts.tests.test_shard_planner import *  # noqa: F401, F403
