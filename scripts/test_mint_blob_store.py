import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "mint_blob_store.py"
_spec = importlib.util.spec_from_file_location("mint_blob_store", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class MintBlobStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = mod.MintBlobStore("host", "user", "/srv/xf")

    def test_blob_path(self):
        sha256 = "a1b2c3d4e5"
        path = self.store.blob_path(sha256)
        self.assertEqual(path, "/srv/xf/artifacts/blob-store/sha256/a1/a1b2c3d4e5")

    def test_temp_path(self):
        sha256 = "a1b2c3d4e5"
        path = self.store.temp_path(sha256)
        self.assertEqual(path, "/srv/xf/temp-upload/a1b2c3d4e5.tmp")

    def test_manifest_path(self):
        path = self.store.manifest_path("run-123")
        self.assertEqual(path, "/srv/xf/artifacts/runs/run-123/manifest.json")

if __name__ == "__main__":
    unittest.main()
