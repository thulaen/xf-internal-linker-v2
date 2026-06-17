from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import image_refs


class RunnerImageRefsTests(unittest.TestCase):
    def test_lockfile_renders_digest_refs_for_all_runners(self) -> None:
        refs = image_refs.refs_by_runner()

        self.assertEqual(set(refs), set(image_refs.REQUIRED_RUNNERS))
        for ref in refs.values():
            self.assertIn("@sha256:", ref)
            self.assertNotIn(":latest", ref)

    def test_configmap_uses_lockfile_refs_without_copying_tags(self) -> None:
        manifest = image_refs.render_configmap(
            image_refs.refs_by_runner(),
            name="runner-image-refs",
            namespace="xf-test",
        )

        self.assertIn("name: runner-image-refs", manifest)
        self.assertIn("namespace: xf-test", manifest)
        self.assertIn("python.image: 10.10.10.91:5000/xf-runner-python@sha256:", manifest)
        self.assertNotIn(":v1", manifest)

    def test_rejects_repository_with_tag(self) -> None:
        runners = {
            name: {
                "repository": f"10.10.10.91:5000/xf-runner-{name}",
                "digest": "sha256:" + "a" * 64,
            }
            for name in image_refs.REQUIRED_RUNNERS
        }
        runners["python"]["repository"] = "10.10.10.91:5000/xf-runner-python:v1"
        lockfile = _write_lockfile({"runners": runners})

        with self.assertRaisesRegex(ValueError, "repository must not include a tag"):
            image_refs.refs_by_runner(lockfile)

    def test_rejects_short_or_non_hex_digest(self) -> None:
        for digest in ("sha256:x", "sha256:" + "g" * 64):
            with self.subTest(digest=digest):
                lockfile = _write_lockfile(_lockfile_with_digest(digest))
                with self.assertRaisesRegex(ValueError, "64 lowercase hex"):
                    image_refs.refs_by_runner(lockfile)


def _write_lockfile(data: dict) -> Path:
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "runner-images.lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    _TEMP_DIRS.append(temp_dir)
    return path


_TEMP_DIRS: list[tempfile.TemporaryDirectory] = []


def _lockfile_with_digest(digest: str) -> dict:
    return {
        "runners": {
            name: {
                "repository": f"10.10.10.91:5000/xf-runner-{name}",
                "digest": digest,
            }
            for name in image_refs.REQUIRED_RUNNERS
        }
    }


if __name__ == "__main__":
    unittest.main()
