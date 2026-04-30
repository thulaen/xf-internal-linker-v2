"""Aho-Corasick multi-pattern matcher for fast anchor scanning.

Reference
---------
Aho, A. V., & Corasick, M. J. (1975). "Efficient Bibliographic Search:
A Long-lived Pattern Matching Algorithm." Communications of the ACM.
DOI: 10.1145/360827.360855
"""

from __future__ import annotations

from dataclasses import dataclass
import ahocorasick


@dataclass(frozen=True, slots=True)
class PatternMatch:
    """A single pattern match in text."""

    pattern: str
    start: int
    end: int
    value: any = None


class AhoCorasickMatcher:
    """High-performance multi-pattern scanner.

    Wraps ``ahocorasick.Automaton`` to provide a clean API for
    simultaneous searching of thousands of patterns.
    """

    def __init__(self, case_sensitive: bool = False):
        self.automaton = ahocorasick.Automaton()
        self.case_sensitive = case_sensitive
        self._built = False

    def add_pattern(self, pattern: str, value: any = None) -> None:
        """Add a pattern to the dictionary."""
        if self._built:
            raise RuntimeError("Cannot add patterns to a built automaton.")
        if not pattern:
            return

        key = pattern if self.case_sensitive else pattern.lower()
        # Automaton.add_word returns False if the word was already there.
        # We store the original pattern and value as a tuple.
        self.automaton.add_word(key, (pattern, value))

    def build(self) -> None:
        """Construct the trie and failure links."""
        if not self._built:
            self.automaton.make_automaton()
            self._built = True

    def find_all(self, text: str) -> list[PatternMatch]:
        """Find all occurrences of all patterns in text.

        Note: finds overlapping matches.
        """
        if not self._built:
            self.build()

        search_text = text if self.case_sensitive else text.lower()
        matches: list[PatternMatch] = []

        # iter returns (end_index, (original_pattern, value))
        for end_idx, (original_pattern, value) in self.automaton.iter(search_text):
            # ahocorasick's end_idx is inclusive.
            start_idx = end_idx - len(original_pattern) + 1
            matches.append(
                PatternMatch(
                    pattern=original_pattern,
                    start=start_idx,
                    end=end_idx + 1,
                    value=value,
                )
            )

        return matches

    def find_non_overlapping(self, text: str) -> list[PatternMatch]:
        """Find non-overlapping matches using a longest-match-first strategy.

        This is crucial for anchor extraction where we don't want to link
        "Artificial Intelligence" and "Intelligence" separately if they overlap.
        """
        all_matches = self.find_all(text)
        if not all_matches:
            return []

        # Sort by length (descending) to prefer longest matches.
        # Secondary sort by start index (ascending).
        all_matches.sort(key=lambda m: (-(m.end - m.start), m.start))

        final_matches: list[PatternMatch] = []
        occupied_offsets: set[int] = set()

        for match in all_matches:
            # Check if any character in this match's range is already taken.
            match_range = range(match.start, match.end)
            if any(idx in occupied_offsets for idx in match_range):
                continue

            final_matches.append(match)
            occupied_offsets.update(match_range)

        # Sort results by position for the caller.
        final_matches.sort(key=lambda m: m.start)
        return final_matches
