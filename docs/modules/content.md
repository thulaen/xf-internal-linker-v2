# Module: content

**Layer:** 1 (foundation).
**Status:** Stub — full detail lands in slice 4.
**Maps to today:** `backend/apps/content/`, parts of `backend/apps/audit/` that touch content rows, anchor-phrase services.

## Plain-English summary

The content module owns the things the linker reads and writes against: posts, pages, threads, anchor phrases, distilled text. Anything that *is* a piece of content — or a piece of metadata directly about a piece of content — lives here.

Sources put content into this module. Pipeline reads content from this module. Suggestions point at content owned by this module.

## Public interface

`content.api` exports the records the rest of the codebase reads. Examples slated for slice 4:

- `Post`, `Page`, `Thread`
- `AnchorPhrase`
- `DistilledText`
- `get_post(id: int) -> Post | None`
- `iter_recent_posts(since: datetime) -> Iterable[Post]`
- `distill(content_id: int, content_type: str) -> DistilledText`

The full list lands in slice 4. Private files inside `apps.content` are not callable from outside.

## Job (the "and"-test)

Content owns one job: **the content model the linker reads and writes against.** If the function is about how content gets in (that is sources), how content is scored (pipeline), or how a suggestion is reviewed (suggestions), it does not belong here.

## Owned tables

- `Post`, `Page`, `Thread` (and similar content rows)
- `AnchorPhrase`
- `DistilledText`
- The content-type lookup tables and the `(content_id, content_type)` composite-key glue

The full list arrives with the slice-4 move.

## Dependencies

- `platform` (settings, audit logging, hardware profile)

Content does **not** depend on `sources`, `pipeline`, `suggestions`, `analytics`, `graph`, `operations`, or `governance`. It is a sibling of `sources` at Layer 1.

## Open questions

- Where does the per-content embedding cache live — in `content` (close to the row) or `pipeline` (close to the consumer)? Current lean: a small `EmbeddingCacheEntry` row in `content`, populated by `pipeline`.
- The plain-English glossary uses "distilled text" — confirm the type name matches the glossary entry exactly. (See `PLAIN-ENGLISH-RULE.md` glossary.)

## Citations

- Parnas 1972 — information hiding for the central data model.
- Yamaguchi 2014 — code property graphs (relevant when the content table participates in cross-module fitness checks).

## Slice that moves this module

Slice 4. Lands after `platform` so other modules can depend on a stable `content.api`.
