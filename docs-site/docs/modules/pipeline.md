---
id: pipeline
title: Pipeline Module
---

# Pipeline Module

The Pipeline module (`backend/apps/pipeline`) is responsible for orchestrating background jobs and managing data flow between the content sources and the suggestion engine.

## Background Jobs

Long-running and scheduled work (crawling, text extraction, embedding, ranking) runs through Celery workers. Cross-module communication uses direct calls into each module's `api.py` — there is no event bus (see ADR 0004).
