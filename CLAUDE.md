# Claude Instructions

When responding to the user in this repository:

- Talk in plain English.
- Explain things like the user is five.
- Give the simple explanation first.
- Prefer short sentences and everyday words.
- Define technical terms immediately if they are needed.

# Docker Rules — No Exceptions

Every AI session must follow these rules to prevent Docker disk bloat:

- Never add a `build:` block to a service that can reuse an existing image. Use `image:` instead.
- The build-once pattern is mandatory: `xf-linker-backend:latest` is shared by backend, celery-worker, and celery-beat. `xf-linker-http-worker:latest` is shared by http-worker-api and http-worker-queue. Do not break this.
- After any `docker-compose build`, immediately run `docker image prune -f` to remove dangling images (old leftover copies).
- Never run `docker-compose down -v` — the `-v` flag deletes the database and all embeddings. Use `docker-compose down` only (no `-v`).
