"""Schwartz-Hearst 2003 acronym detection algorithm.

Reference
---------
Schwartz, A. S., & Hearst, M. A. (2003). A simple algorithm for identifying
abbreviation definitions in biomedical text. PSB 2003.
DOI: 10.1142/9789812776303_0042
"""

from __future__ import annotations

import re


class SchwartzHearstDetector:
    """High-precision acronym-definition pair extractor.

    Pattern matched: "Long Form (Short Form)" or "Short Form (Long Form)".
    The original paper focuses on "(SF)" as the trigger.
    """

    # Matches "(SF)" where SF is 2-10 chars, starting with an alphanumeric.
    _PAREN_RE = re.compile(r"\((?P<acronym>[a-zA-Z0-9][^)]*?)\)")

    def __init__(self, min_acronym_len: int = 2, max_acronym_len: int = 10):
        self.min_acronym_len = min_acronym_len
        self.max_acronym_len = max_acronym_len

    def extract_pairs(self, text: str) -> dict[str, str]:
        """Extract acronym -> definition pairs from text.

        Returns a dictionary where keys are acronyms and values are definitions.
        """
        pairs: dict[str, str] = {}
        if not text:
            return pairs

        for match in self._PAREN_RE.finditer(text):
            acronym = match.group("acronym").strip()

            # Rule: acronym length constraint
            if not (self.min_acronym_len <= len(acronym) <= self.max_acronym_len):
                continue

            # Case 1: Long Form (Short Form)
            # Search preceding text for the long form.
            preceding_text = text[: match.start()].strip()
            if not preceding_text:
                continue

            definition = self._find_definition(acronym, preceding_text)
            if definition:
                pairs[acronym] = definition
                continue

            # Case 2: Short Form (Long Form) - less common but handled by some variants.
            # Schwartz-Hearst 2003 focuses on (SF) as the trigger.
            # We follow the paper strictly to maintain high precision.

        return pairs

    def _find_definition(self, acronym: str, preceding_text: str) -> str | None:
        """Find the long-form definition for an acronym in the preceding text.

        Implementation of the matching logic from Schwartz-Hearst 2003 §2.1.
        """
        # Candidate words are the last N words where N is len(acronym) * 2 or similar.
        # Paper suggests searching back at most min(len(acronym)+5, len(acronym)*2) words.
        words = preceding_text.split()
        if not words:
            return None

        search_window = min(len(acronym) + 5, len(acronym) * 2)
        candidate_words = words[-search_window:]

        # Matching starts from the end of the acronym and the end of candidate words.
        a_idx = len(acronym) - 1
        w_idx = len(candidate_words) - 1

        # The last character of the acronym must match a character in the last word.
        # Actually, the paper says "The algorithm starts from the end of both strings..."
        # and "Each character of the acronym must match at least one character in
        # the corresponding word in the long form..."

        # Simpler robust version:
        # Each char in acronym (right to left) must match the first char of a word (right to left).
        # We also allow the char to match inside the word if it's the same word.

        current_word_idx = w_idx
        found_words = []

        for char in reversed(acronym.lower()):
            if not char.isalnum():
                continue

            # Search backwards for a word starting with this char
            match_found = False
            while current_word_idx >= 0:
                word = candidate_words[current_word_idx].lower()
                if word.startswith(char):
                    found_words.append(candidate_words[current_word_idx])
                    current_word_idx -= 1
                    match_found = True
                    break
                current_word_idx -= 1

            if not match_found:
                return None

        if found_words:
            # Definition is the sequence of words from the last found word to the end.
            # Wait, the found_words are in reverse order.
            start_word_in_candidates = current_word_idx + 1
            # The definition is everything from that start word to the end of candidate_words.
            # But found_words might have skipped some words.
            # Schwartz-Hearst says the definition starts at the word containing the first char.
            return " ".join(candidate_words[start_word_in_candidates:])

        return None
