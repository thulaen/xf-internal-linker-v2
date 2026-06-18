"""Tests for resolving sidecar images into digest-pinned references."""

from __future__ import annotations

import subprocess
import unittest

import resolve_sidecar_image_digests as resolver


DIGEST = "sha256:" + ("a" * 64)


def _completed(args: list[str], returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


class ResolveSidecarImageDigestTests(unittest.TestCase):
    def test_tagged_image_is_rewritten_to_digest_reference(self) -> None:
        pinned = resolver.pin_image_reference("registry.local:5000/xf/streamd:ready", DIGEST)

        self.assertEqual(pinned, f"registry.local:5000/xf/streamd@{DIGEST}")

    def test_missing_image_reference_fails_before_docker_inspect(self) -> None:
        with self.assertRaisesRegex(ValueError, "streamd image reference is missing"):
            resolver.resolve_images({"streamd": "", "startupd": "x", "sidecars": "x"})

    def test_resolve_images_uses_docker_digest_output(self) -> None:
        calls: list[list[str]] = []

        def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            return _completed(args, 0, stdout=f"Name: image\nDigest: {DIGEST}\n")

        result = resolver.resolve_images(
            {
                "streamd": "registry.local/xf/streamd:ready",
                "startupd": "registry.local/xf/startupd:ready",
                "sidecars": "registry.local/xf/sidecars:ready",
            },
            runner,
        )

        self.assertEqual(len(calls), 3)
        self.assertEqual(result["sidecars"], f"registry.local/xf/sidecars@{DIGEST}")


if __name__ == "__main__":
    unittest.main()
