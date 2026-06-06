"""Property tests for sentence splitting."""

from django.test import SimpleTestCase
from apps.pipeline.services.sentence_splitter import split_sentences

class SentenceSplitterPropertyTests(SimpleTestCase):

    def test_abbreviations_do_not_split(self):
        # Abbreviations (Dr., e.g., i.e., etc., Mr., Mrs.) do not always create sentence breaks.
        text = "Dr. Smith went to the store. He bought apples, e.g. granny smiths, and pears."
        sents = split_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertTrue(sents[0].startswith("Dr. Smith"))
        self.assertTrue(sents[1].startswith("He bought"))

    def test_urls_do_not_split(self):
        # URLs do not create bogus sentence breaks.
        text = "Visit https://example.com/foo.html for more info. It is a great site."
        sents = split_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertEqual(sents[0], "Visit https://example.com/foo.html for more info.")
        self.assertEqual(sents[1], "It is a great site.")

    def test_decimal_numbers_do_not_split(self):
        # Decimal numbers (3.14, 99.9%) do not split sentences.
        text = "The value of pi is approx 3.14159. The success rate is 99.9%."
        sents = split_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertEqual(sents[0], "The value of pi is approx 3.14159.")
        self.assertEqual(sents[1], "The success rate is 99.9%.")

    def test_forum_signatures_ignored(self):
        # Forum signatures (-- Joe, ~~ JaneDoe) do not become linkable content.
        text = "This is a valid sentence that should be kept. -- Joe"
        sents = split_sentences(text)
        self.assertEqual(len(sents), 1)
        self.assertEqual(sents[0], "This is a valid sentence that should be kept.")

    def test_very_short_fragments_filtered(self):
        # Very short fragments (<= 3 chars) are filtered. (In reality < 15 chars)
        text = "Hi.\n\nThis sentence is long enough to be kept.\n\nOk."
        sents = split_sentences(text)
        self.assertEqual(len(sents), 1)
        self.assertEqual(sents[0], "This sentence is long enough to be kept.")

    def test_empty_input(self):
        # Empty input yields an empty list (does not crash).
        self.assertEqual(split_sentences(""), [])
        self.assertEqual(split_sentences("   "), [])
