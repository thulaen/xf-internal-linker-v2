# Runbook library

Phase MX3 / Gap 339.

Each file in this directory is a short runbook keyed by the error
pattern that should trigger it. Filenames follow:

    <job_type>-<step>.md

so the error-intelligence layer (Phase MX2 / Gap 320) can deep-link
from any ErrorLog row by building the slug from
`error.job_type + '-' + error.step`.

## Contract

Every runbook MUST open with a single-line `## Symptom` heading, a
`## Root cause` paragraph, and numbered remediation steps. A final
`## Verify` section describes the automated check that confirms the
fix held.

Example skeleton:

```markdown
## Symptom
CUDA OOM crash during the embed stage.

## Root cause
Batch size too large for the current GPU + concurrent process.

## Fix
1. Open Settings → Performance Mode → switch to **Safe**.
2. Lower `embed.batch_size` from 32 to 16.
3. Restart the embed worker: `docker compose restart celery-embed`.

## Verify
Re-run the pipeline. The Performance Dashboard should show the
embed stage completing under 2 min with no OOM in `ErrorLog`.
```

## Naming conventions

- `pipeline-embed.md` — embed-stage failures
- `pipeline-index.md` — FAISS index rebuild issues
- `import-xenforo.md` — XenForo sync failures
- `import-wordpress.md` — WordPress sync failures
- `integration-gsc.md` — GSC auth / token expiry
- `integration-ga4.md` — GA4 auth / quota issues
- `integration-matomo.md` — Matomo auth / unreachable
- `infra-redis.md` — Redis connectivity
- `infra-celery.md` — worker crashed / queue backed up

Add new runbooks freely — the Error Log UI surfaces any file matching
the slug, whether or not a maintainer pre-registered it.
