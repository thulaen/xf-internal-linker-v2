# Safe Docker Rebuild — One Button, No Lost Logins

This page is for the operator. It explains how to rebuild Docker without losing your admin account, your embeddings, your XenForo / WordPress imports, or any other data living in the `pgdata` volume.

## Use this script every time

```powershell
.\scripts\safe-rebuild.ps1
```

That's it. It does the same thing as `docker compose --env-file .env up --build`, plus eight safety steps wrapped around it. **Stop using `docker compose` directly for rebuilds.** The bare commands are still fine for `up -d` (start a stopped stack) and `down` (stop a running stack), but for **rebuilding**, this script is the only sanctioned path.

## What the script does, step by step

1. **Pre-flight: pgdata volume must exist.** Looks up `xf-internal-linker-v2_pgdata` with `docker volume inspect`. If it's missing, the script refuses to continue. A missing volume on a rebuild is the single most-common cause of "I can't log in anymore" — the rebuild would create a brand-new empty database. If this happens to you, restore from a snapshot in `backups/` before rebuilding.
2. **Fresh snapshot.** Calls `manage.py backup_db_now` inside the live backend container. Writes a compressed Postgres dump to `backups/snapshot-YYYYMMDD-HHMMSS.dump`. Refuses to continue if the snapshot fails (usually low free disk).
3. **Baseline user count.** Calls `manage.py verify_users_present --min 0` and captures the current `auth_user` row count. This is the number we'll re-check after the rebuild.
4. **Safe stop.** Runs `docker compose down`. **Never `-v`.** That single flag is what deletes pgdata; the script will not pass it.
5. **Build + start.** Runs `docker compose --env-file .env up --build -d`. New images, same named volumes.
6. **Prune.** `docker system prune -f`. Removes stopped containers, dangling images, and build cache. **Named volumes are never touched** — your data is safe.
7. **Wait for healthy.** Polls `docker inspect xf_linker_backend` until the healthcheck reports `healthy`. Times out after 180 s by default (override with `-HealthcheckTimeoutSeconds N`).
8. **Post-flight verify.** Runs `manage.py verify_users_present --min <baseline>`. If the count dropped below the baseline, the script prints a red banner and tells you how to restore from the snapshot it just took.

If everything is fine you see a green banner: **GREEN: rebuild safe. auth_user count preserved at \<N\>.**

## If the script stops red

You'll see one of three messages:

- **"The pgdata volume is missing."** Don't rebuild. The volume already vanished. Restore from a snapshot (`docker compose exec backend python manage.py restore_db_snapshot --latest --confirm`) or, if this is a genuine first checkout, run `.\scripts\start.ps1` instead.
- **"Snapshot failed."** Free up disk and re-run. The snapshot helper refuses to write when free space drops below 5 GB.
- **"auth_user count dropped below the baseline."** A user disappeared during the rebuild. Either re-run with `-AutoRestore` to roll back to the snapshot the script just took, or run the restore yourself: `docker compose exec backend python manage.py restore_db_snapshot --latest --confirm`.

## "I lost my login anyway"

You won't if you use the script. But if you're reading this because you already lost access:

1. Open `https://localhost/` in your browser. If the title says "Create admin sign-in" instead of "Sign in", you're on a fresh DB — type `admin` plus the password you want, click the button, and you're back in. The frontend wizard handles the create-the-first-admin path automatically.
2. If the title says "Sign in" but credentials are rejected, the front-end's first-operator probe failed silently. Force the recovery from a terminal:
   ```powershell
   docker compose exec -T backend curl -sS -X POST http://127.0.0.1:8000/api/auth/first-operator/ `
     -H "Content-Type: application/json" `
     -d "{\"username\":\"admin\",\"password\":\"<your password>\",\"email\":\"admin@example.com\"}"
   ```
   That call goes through the loopback inside the container (so the locality check passes) and creates the account.
3. If `backups/` already contains snapshots from a prior session, restore the most recent one:
   ```powershell
   docker compose exec backend python manage.py restore_db_snapshot --latest --confirm
   ```
   Your old admin row comes back with the password it had at snapshot time.

## Why pgdata now has a fixed external name

`docker-compose.yml` maps the app's `pgdata` volume to the fixed external Docker volume `xf-internal-linker-v2_pgdata`. This means a project folder rename or a Compose project-name change no longer creates a second empty database volume.

It also means `docker compose down -v` no longer removes the main database volume through Compose. Docker Desktop factory resets and direct Docker volume deletion can still remove the volume, but startup now stops when backups exist and the protected volume is missing. That prevents the app from silently booting into a blank database.

Fresh checkouts with no backups are still allowed: `scripts/start.ps1` creates the fixed protected volume once, then starts the stack.

## Why we never use `down -v`

The `-v` flag tells Docker to delete every named volume Compose owns. The main `pgdata` database volume is now external, so Compose should not delete it, but the flag can still remove other app volumes such as `redis-data`, `media_files`, `frontend_dist`, and `staticfiles`. Wiping Redis clears Celery results and the rate-limit counters. Wiping media deletes uploaded assets. **There is no scenario where we need `-v`.** If you genuinely need to start over, delete the volumes by name with explicit confirmation, never with `down -v`.

## Same credentials, two surfaces

Your admin account is one row in the Postgres `auth_user` table. The `create_superuser()` call sets `is_staff=True` and `is_superuser=True`. That single row authenticates you on both:

- **The Angular SPA** at `https://localhost/` via the DRF token endpoint `/api/auth/token/`.
- **Django admin** at `https://localhost/admin/` via the standard Django session login.

Verify any time:

```powershell
docker compose exec -T backend python manage.py shell -c `
  "from django.contrib.auth import get_user_model as g; u=g().objects.get(username='admin'); `
   import json; print(json.dumps({'is_staff': u.is_staff, 'is_superuser': u.is_superuser, 'has_pw': u.has_usable_password()}))"
```

Expected: `{"is_staff": true, "is_superuser": true, "has_pw": true}`.

## When the startup check fires

If the backend boots and finds `auth_user` empty AND `backups/` already contains snapshots, you'll see a `core.W001` warning in `manage.py check` output and in the backend startup log:

> auth_user is empty, but backups/ already contains snapshots — this almost always means a Docker rebuild lost the pgdata volume.

It's a hint, not a hard error. The recovery path is the same as the "I lost my login anyway" section above.
