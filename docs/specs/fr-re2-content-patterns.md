# RE2 for untrusted-content regex patterns — spec

[SPEC FRESHNESS: reviewed_at=2026-06-13 next_review=2026-09-13]
[SPEC CITED: feature=re2-content-patterns kind=technical_doc id=https://github.com/google/re2/wiki/Syntax verified_at=2026-06-13]

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | RE2 link-parser patterns |
| **Module** | `backend/apps/pipeline/services/link_parser.py` (five compiled patterns) |
| **Tests** | `backend/apps/pipeline/tests_re2_parity.py` (permanent `re` ↔ RE2 parity suite) |
| **Dependency** | `google-re2==1.1.20240702` (runtime image; imports as `re2`) |
| **Default state** | Always on — the five patterns are RE2-compiled at import (one-way swap from `re`). |

## 2 · Problem

Five link-parser patterns run over UNTRUSTED input — raw crawled HTML, forum
BBCode, and external URLs. Python's built-in `re` is a backtracking engine: a
pattern with `.*?` and alternation can be driven into exponential
("catastrophic") backtracking by a crafted input, hanging the worker — a
regular-expression denial of service (ReDoS).

## 3 · Approach

Move those five patterns to RE2 (`google-re2`), a finite-automaton engine whose
match time is linear in the input length, so no input can trigger catastrophic
backtracking. RE2 omits lookbehind, lookahead, and backreferences; none of the
five patterns use those features, so the pattern **text is unchanged** — only
the engine differs:

- `_XF_THREAD_RE`, `_XF_RESOURCE_RE` — thread / resource id from a URL path
- `_BBCODE_URL_RE` — `[URL=…]…[/URL]` in crawled BBCode
- `_HTML_LINK_RE` — `<a href=…>…</a>` in crawled HTML
- `_CONTEXT_TOKEN_RE` — word-token presence in a content window

## 4 · Scoped exception

`backend/apps/pipeline/services/phrase_matching.py::_SEGMENT_SPLIT_RE` stays on
stdlib `re`. Its `(?<=[.!?])\s+` lookbehind keeps sentence punctuation attached
to the preceding segment, and RE2 has no lookbehind; a lookbehind-free rewrite
would change the split output. The pattern is already linear-time
(`\r?\n+` / `\s+`, no nested quantifiers), so there is no ReDoS risk to remove.
This is scoping, not a fallback — there is one engine per pattern.

## 5 · Behaviour preserved (parity)

`tests_re2_parity.py` compiles each production RE2 pattern AND the identical
pattern string under stdlib `re`, then asserts equal `search()` and
`finditer()` group output across a fixture corpus that includes ordinary
content and adversarial long-repetition inputs. The suite is permanent: it
fails loudly if a future edit diverges the engines or silently reverts a
pattern to `re`.

## 6 · References

- RE2 syntax — https://github.com/google/re2/wiki/Syntax
- Cox, "Regular Expression Matching Can Be Simple And Fast" — https://swtch.com/~rsc/regexp/regexp1.html
- OWASP, Regular expression Denial of Service (ReDoS) — https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS
