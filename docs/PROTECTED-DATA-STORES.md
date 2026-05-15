# Protected Data Stores

This file lists data that self-pruning must never delete.

## Protected Docker Volumes

- `pgdata` stores the main PostgreSQL database, embeddings, and future Apache AGE graph data.
- `redis-data` stores Redis data.
- `media_files` stores uploaded or generated media.
- `staticfiles` stores collected backend static files.
- `frontend_dist` stores the built Angular app served by nginx.
- `compiled_artifacts` stores current Docker-built C++ and future Go helper outputs. It is
  content-addressed: `/opt/xf/compiled/store/` keeps one copy by SHA-256 hash, and
  `/opt/xf/compiled/active/` keeps the verified runtime view loaded by the app.
- `pyroscope_data` stores performance history.
- `loki_data` stores log history.
- `alloy_data` stores log shipper state.
- `tempo_data` stores trace history.
- `grafana_data` stores Grafana state.
- `questdb_data` is reserved for future QuestDB time-series data.
- `sqlite_registry_data` is reserved for the future SQLite agent-memory registry.

## Protected Host Paths

- `backups/` and `backend/backups/` store database backups.
- `media/`, `backend/data/`, and `data/` may store operator data.
- `backend/secrets/`, `secrets/`, `.env`, and credential files store secrets.
- `nginx/certs/` stores local certificates.
- `Inspiration-Temp/` stores user-owned reference screenshots.
- `grafana/`, `tempo/`, and `postgres/` store service configuration.
- `frontend/src/assets/` stores frontend source assets.
- `backend/registry/data/` and `backend/registry/backups/` are reserved for the future SQLite agent-memory registry and its backups.
- `backend/telemetry/data/` and `backend/telemetry/backups/` are reserved for future time-series telemetry data and backups.

## Future Vital Data Rule

Any new app data, database, graph store, index, uploaded media store, registry, or long-lived observability store must be added to `config/protected-data-stores.json` before any cleanup script may touch nearby paths.

Apache AGE stores graph data inside PostgreSQL, so it is protected by `pgdata`.

## Safe Cleanup Rule

Self-pruning may delete disposable build cache, test cache, old generated reports, and
quality-run scratch folders only after useful results are imported as compact evidence.
It must never run `docker volume prune`, `docker volume rm`, or `docker compose down -v`.
