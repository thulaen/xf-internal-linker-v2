"""Paper trail — database-backed deferred-work tracker.

Separate from AutoIssue (which tracks discovered problems). Paper trail
captures work that was explicitly deferred, with a high-detail abstract
explaining why, plus dedup via a fast C++ MinHash + LSH index so the
same deferral re-filed by different agents collapses into one row.

See docs/PAPER-TRAIL.md for the operator-facing spec.
"""
