# Pick #61 — Double Metaphone (Phonetic Keys)

## 1. Goal Description
Implement phonetic encoding using the Double Metaphone algorithm to improve typo-tolerance and matching accuracy for names, terms, and phrases that sound similar but are spelled differently.

## 2. Math & Logic
- **Algorithm**: Double Metaphone (Philips, 2000).
- Produces a primary and secondary phonetic key (e.g., "Schmidt" -> "XMT", "SMT").
- **Citation**: Philips, L. (2000). "The Double Metaphone Search Algorithm."

## 3. Implementation
- Uses the `metaphone` library.
- Applied to titles and extracted noun-chunks.
- Phonetic keys stored in `nlp_metadata`.

## 4. Verification Plan
- Verify that "Smith" and "Smyth" produce matching primary or secondary keys.
- Verify that non-English terms produce reasonable secondary keys.
