from django.test import SimpleTestCase
from apps.sources.normalize import nfkc, nfkc_all, is_normalised

class NormalizePropsTests(SimpleTestCase):
    def test_nfkc_idempotency(self):
        """Invariant: clean(clean(x)) == clean(x)."""
        text = "café"
        first = nfkc(text)
        second = nfkc(first)
        self.assertEqual(first, second)

    def test_nfkc_is_normalised(self):
        """Invariant: result is always recognised as normalised."""
        text = "café"
        res = nfkc(text)
        self.assertTrue(is_normalised(res))

    def test_nfkc_all_idempotency(self):
        """Invariant: list normalisation is idempotent."""
        texts = ["café", "hello"]
        first = nfkc_all(texts)
        second = nfkc_all(first)
        self.assertEqual(first, second)

    def test_nfkc_none(self):
        """Invariant: None is handled gracefully."""
        self.assertIsNone(nfkc(None))
        self.assertTrue(is_normalised(None))
