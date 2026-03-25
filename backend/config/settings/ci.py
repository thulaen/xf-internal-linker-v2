"""
CI settings for XF Internal Linker V2.

These mirror the fast, self-contained test settings while keeping migrations
enabled so CI can detect schema drift before deploys.
"""

from .test import *  # noqa: F401, F403

MIGRATION_MODULES = {}
