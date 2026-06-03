"""Convention SimpleTestCase coverage for apps.audit.runtime_context.

`snapshot()` and `local_node_identity()` are best-effort runtime probes
that never raise. These tests run with no DB and fully mocked OS/library
calls. They pin the post-GPU-removal shape with exact-value asserts so a
future edit cannot silently re-add `gpu_available` / `cuda_version`
keys or change the fixed node-role default.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.audit import runtime_context
from apps.audit.runtime_context import local_node_identity, snapshot


class LocalNodeIdentityTests(SimpleTestCase):
    def test_when_env_set_then_uses_overrides(self):
        with patch.dict(
            os.environ, {"NODE_ID": "node-A", "NODE_ROLE": "worker"}, clear=False
        ):
            self.assertEqual(local_node_identity(), ("node-A", "worker"))

    @patch("apps.audit.runtime_context.socket.gethostname", return_value="host-X")
    def test_when_env_absent_then_hostname_and_primary(self, _hostname):
        stripped = {
            k: v for k, v in os.environ.items() if k not in {"NODE_ID", "NODE_ROLE"}
        }
        with patch.dict(os.environ, stripped, clear=True):
            self.assertEqual(local_node_identity(), ("host-X", "primary"))


@override_settings(EMBEDDING_MODEL="bge-m3")
class SnapshotTests(SimpleTestCase):
    @patch("apps.audit.runtime_context.socket.gethostname", return_value="host-Y")
    def test_when_no_gpu_keys_then_only_runtime_keys_present(self, _hostname):
        # The GPU/CUDA probe was removed entirely; assert the exact key set.
        with patch.dict(os.environ, {"NODE_ID": "n1", "NODE_ROLE": "primary"}):
            ctx = snapshot()
        self.assertEqual(
            set(ctx.keys()),
            {
                "node_id",
                "node_role",
                "node_hostname",
                "python_version",
                "embedding_model",
                "spacy_model",
            },
        )

    @patch("apps.audit.runtime_context.socket.gethostname", return_value="host-Y")
    def test_when_gpu_keys_removed_then_absent(self, _hostname):
        ctx = snapshot()
        self.assertNotIn("gpu_available", ctx)
        self.assertNotIn("cuda_version", ctx)
        self.assertNotIn("gpu_name", ctx)

    @patch("apps.audit.runtime_context.socket.gethostname", return_value="host-Z")
    def test_when_called_then_static_fields_exact(self, _hostname):
        with patch.dict(os.environ, {"NODE_ID": "n2", "NODE_ROLE": "worker"}):
            ctx = snapshot()
        self.assertEqual(ctx["node_id"], "n2")
        self.assertEqual(ctx["node_role"], "worker")
        self.assertEqual(ctx["node_hostname"], "host-Z")
        self.assertEqual(ctx["python_version"], sys.version.split()[0])
        self.assertEqual(ctx["embedding_model"], "bge-m3")

    def test_when_spacy_import_fails_then_spacy_model_none(self):
        # Force the spaCy import branch to raise so the except sets None.
        with patch.dict(sys.modules, {"spacy": None}):
            ctx = snapshot()
        self.assertIsNone(ctx["spacy_model"])

    @patch("apps.audit.runtime_context.socket.gethostname", return_value="host-W")
    def test_when_called_then_returns_six_keys(self, _hostname):
        # Contract: snapshot() is called on every error; pin the exact length.
        ctx = snapshot()
        self.assertEqual(len(ctx), 6)


class SnapshotNoRaiseTests(SimpleTestCase):
    def test_when_runtime_module_imported_then_exports_match(self):
        self.assertEqual(runtime_context.__all__, ["local_node_identity", "snapshot"])
