# Bug Fix Report: C# Import Page Cap

**Date:** 2026-04-11  
**Trigger:** `PipelineServices.cs` changed (per Business Logic Checklist § 4.4)  
**Files changed:** `PipelineServices.cs`, `HttpWorkerOptions.cs`, `appsettings.json`

## What Changed

Replaced three hardcoded `for (int page = 1; page <= 5; page++)` loop ceilings in
`ImportContentService.ExecuteAsync()` — one each for XenForo threads, XenForo resources,
and WordPress posts/pages — with `page <= _importMaxPages`.

`_importMaxPages` is sourced from `IOptions<HttpWorkerOptions>` →
`HttpWorkerOptions.Http.ImportMaxPages`, which defaults to `100` in both
`HttpWorkerOptions.cs` and `appsettings.json`.

Added per-page `LogInformation` inside each loop so operators can see pagination progress
without reading source code.

## Why

Forums and WordPress sites with more than 5 pages of content were silently truncated.
The Python Celery importer already uses a configurable `import.max_pages` setting (default
500 via `AppSetting`), so the C# import lane was the only path with a fixed ceiling.
This caused silent corpus bias on any scope with more than 5 index pages: embeddings,
link graphs, and ranker signals all downstream of import were built on incomplete data.

## Academic Grounding

Configurable crawl depth is standard practice in focused web crawlers. The pattern
follows the existing Python import implementation in `tasks_import.py` (same project).
See also: Chakrabarti (2002) *Mining the Web*, §3.2 — depth parameters for focused
crawlers.

## Regression Risk

**None.** The new default (`ImportMaxPages: 100`) replaces the old hardcoded `5`.
Operators who need the previous cap can set `HttpWorker:Http:ImportMaxPages: 5` in their
environment configuration without any code changes. No database schema changes.
No changes to any downstream service.

## Benchmark

Not required. This is an I/O-bound network loop (awaiting HTTP responses from external
XenForo/WordPress APIs). The inner loop body is identical to the original — no CPU
hot-path logic changed.
