import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-frontend-routes.py"
_spec = importlib.util.spec_from_file_location("check_frontend_routes", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckFrontendRoutesTests(unittest.TestCase):
    def test_to_regex_path(self):
        # path('foo/<int:pk>/bar/', ...)
        pattern = "foo/<int:pk>/bar/"
        rx = mod.to_regex(pattern)
        self.assertTrue(rx.match("/foo/123/bar/"))
        self.assertTrue(rx.match("/foo/123/bar"))
        self.assertFalse(rx.match("/foo/bar/"))

    def test_to_regex_re_path(self):
        # re_path(r'^foo/(?P<slug>[-\w]+)/$', ...)
        pattern = r"^foo/(?P<slug>[-\w]+)/$"
        rx = mod.to_regex(pattern)
        self.assertTrue(rx.match("/foo/my-slug/"))

    def test_url_matches(self):
        rx = mod.to_regex("prune/safe/")
        self.assertTrue(mod.url_matches("/api/prune/safe/", [rx]))
        self.assertTrue(mod.url_matches("prune/safe/", [rx]))
        self.assertFalse(mod.url_matches("/api/prune/unsafe/", [rx]))

if __name__ == "__main__":
    unittest.main()
