"""Unit tests for the Library Expansion Bank markdown parser.

The parser turns the curated ledger
(docs/specs/fr-approved-library-expansion-bank.md) into plain dataclasses.
It must be Django-free so it tests fast in isolation, and it must only treat
`#### NNN.` blocks under `## 5. Library registry` as library cards (never the
`### Slice NNN` headers).
"""

from __future__ import annotations

import pytest

from apps.library_registry.services.parser import parse_document

pytestmark = pytest.mark.unit


_FIXTURE = """\
## 4. Capability recipes

### Need live vector retrieval

Use search_index.api with pgvector first. Use USearch only in a bake-off.

### Need duplicate detection

Use BLAKE3 or XXH3 for fast fingerprints.

## 5. Library registry

### A. Columnar and dataset execution

#### 001. Apache Arrow
- Lane: C++/Rust/Python via ranking_training, metadata_catalog.
- Use: share columnar memory between engines.
- Avoid: use it as the active profile store.
- Pair: Parquet, DuckDB.
- Gate: ADR, tests, pin, security.

#### 002. DuckDB
- Lane: C++/Python via ranking_training.
- Use: join local Parquet evidence offline.
- Avoid: serve live suggestions.
- Pair: Parquet, Ibis.
- Gate: ADR, tests, pin.

### B. Search and retrieval

#### 003. Tantivy
- Lane: Rust via search_index.
- Use: full-text search without a JVM.
- Avoid: store the source of truth.
- Pair: Postgres FTS.
- Gate: ADR, tests, pin, bench.

## 6. Implementation slices

### Slice 001 - something
This should not be parsed as a library.
"""


def test_parses_every_library_card() -> None:
    bank = parse_document(_FIXTURE)
    names = [lib.name for lib in bank.libraries]
    assert names == ["Apache Arrow", "DuckDB", "Tantivy"]


def test_slice_headers_are_not_libraries() -> None:
    bank = parse_document(_FIXTURE)
    # `### Slice 001` is a level-3 header, not a `#### NNN.` card.
    assert all("Slice" not in lib.name for lib in bank.libraries)
    assert all(lib.number in (1, 2, 3) for lib in bank.libraries)


def test_first_card_captures_all_bullet_fields() -> None:
    arrow = parse_document(_FIXTURE).libraries[0]
    assert arrow.number == 1
    assert arrow.section_letter == "A"
    assert arrow.section_title == "Columnar and dataset execution"
    assert "C++/Rust/Python" in arrow.lane
    assert arrow.use == "share columnar memory between engines."
    assert arrow.avoid == "use it as the active profile store."
    assert arrow.pair == "Parquet, DuckDB."
    assert arrow.gate == "ADR, tests, pin, security."


def test_section_letter_follows_the_card() -> None:
    tantivy = parse_document(_FIXTURE).libraries[2]
    assert tantivy.section_letter == "B"
    assert tantivy.section_title == "Search and retrieval"


def test_parses_capability_recipes() -> None:
    recipes = parse_document(_FIXTURE).recipes
    titles = [r.title for r in recipes]
    assert titles == ["Need live vector retrieval", "Need duplicate detection"]


def test_recipe_key_drops_the_need_prefix() -> None:
    first = parse_document(_FIXTURE).recipes[0]
    assert first.key == "live_vector_retrieval"
    assert "pgvector" in first.body


def test_empty_document_yields_no_rows() -> None:
    bank = parse_document("")
    assert bank.libraries == ()
    assert bank.recipes == ()
