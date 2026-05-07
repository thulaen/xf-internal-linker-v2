# Passkeys — Plain-English Setup Guide

A passkey is a small key your browser stores in your laptop's secure chip (Windows Hello, Touch ID, or a hardware key like a YubiKey). When you sign in, the website asks "is the same person here?" and your laptop says yes — without sending any password over the wire. The website never sees the key, so it can't be stolen, phished, or leaked in a database breach.

This page covers the operator-facing pieces: **how to enrol a passkey**, **how to sign in with one**, and **how to manage them afterward**. The technical details live in `backend/apps/core/views_passkey.py` and `frontend/src/app/core/services/passkey.service.ts`.

## One-time setup before you enrol

- The site must be served over HTTPS. The `webauthn` library refuses any origin that isn't `https://...` or `http://localhost`. Our prod-only nginx stack already redirects HTTP → HTTPS at port 80 → 443.
- The `WEBAUTHN_RP_ORIGIN` env var must match exactly what the browser sees. For this stack that's `https://localhost`. The defaults in `.env.example` already set this. If you change the domain, update `.env` and rebuild via `scripts\safe-rebuild.ps1`.
- You must already have a regular admin account (`admin` + password). Passkeys are enrolled **on top of** an existing account; they don't replace the password.

## Enrolling your first passkey

1. Sign in with `admin` + your password at `https://localhost/`.
2. Open `https://localhost/preferences`.
3. Scroll to the "Passkeys" card at the bottom.
4. Click **Add a passkey**.
5. Type a friendly name when the prompt asks ("MacBook Touch ID", "Windows Hello", "YubiKey on keychain", etc).
6. The browser shows the WebAuthn picker. On Windows it offers Windows Hello (fingerprint or PIN). On Mac it offers Touch ID. On Chrome/Edge with a hardware key plugged in, it offers the key.
7. Approve with the fingerprint, face, PIN, or button-press.
8. The new passkey appears in the list with "Last used: Never used yet".

## Signing in with a passkey

1. Sign out (or open a private window).
2. The login screen at `https://localhost/` shows a **Sign in with a passkey** button below the password fields. The button is hidden when:
   - your browser doesn't support WebAuthn,
   - the backend's HEAD probe at `/api/auth/passkey/login/begin/` returns 404 (route not wired),
   - or the first-operator-setup flow is open (you don't have an account yet).
3. Click the button. The browser shows the same picker as during enrolment. Approve.
4. You're signed in. The same DRF token endpoint that backs the password login also issues your token here, so every page in the app works the same.

## Renaming or deleting a passkey

In the same Preferences card:

- **Pencil icon** next to a row → renames it.
- **Trash icon** next to a row → deletes it. The backend refuses to delete your **only** passkey when your account has no usable password (you would lock yourself out). Set a password first if that ever applies.

## Why the button is sometimes hidden

The login screen runs three checks before showing the passkey button:

1. `window.PublicKeyCredential` exists. Older browsers (and a handful of niche WebViews) lack this.
2. The HEAD probe of `/api/auth/passkey/login/begin/` returns anything other than 404. A 503 (library not installed) hides the button; a 200 / 401 / 403 reveals it.
3. The first-operator-setup flow is **not** open. We hide passkey login during the bootstrap step because there's no account to authenticate against yet.

If your button is hidden when you expect it, open the browser devtools, run `await fetch('/api/auth/passkey/login/begin/', {method: 'HEAD'})`, and check the response code. Anything other than 404/503 should reveal the button.

## Debugging from `/admin/`

When something goes wrong (registration fails, a credential won't sign in), you can browse the raw rows from Django admin at `https://localhost/admin/`. Two new sections live under the "Core" app:

- **Passkey credentials** — every enrolled passkey. Columns: user, label, sign_count, last_used_at, created_at. Binary fields (credential_id, public_key) are read-only — don't try to edit them, you'd just corrupt the row.
- **Passkey challenges** — short-lived (5-minute TTL) registration / login challenges. Mostly empty because the finish handlers + the 6-hourly Celery task `core.passkey_cleanup_expired_challenges` prune them. If you see lots of stale rows here, the cleanup task isn't running.

## Common errors and what they mean

| Error | What it means | Fix |
|---|---|---|
| "RP ID mismatch" | The browser sees a different origin than `WEBAUTHN_RP_ORIGIN` says | Set `WEBAUTHN_RP_ORIGIN` in `.env` to match the URL bar (`https://localhost`, not `http://localhost`). Rebuild via `scripts\safe-rebuild.ps1`. |
| "No active registration challenge" | The 5-minute TTL expired between begin and finish | Click "Add a passkey" again, approve within 5 minutes. |
| "Refusing to delete your only passkey" | Lockout safety — you have no usable password | Set a password first (Django admin → users → admin → save), then come back and delete. |
| "WebAuthn library is not installed on this backend" | The `webauthn` package isn't in the running image | Rebuild via `scripts\safe-rebuild.ps1`. The package is in `backend/requirements.txt`. |

## Cross-references

- `backend/apps/core/views_passkey.py` — register/login ceremonies (begin + finish).
- `backend/apps/core/views_passkey_management.py` — list/rename/delete endpoints.
- `backend/apps/core/tasks_passkey_cleanup.py` — every-6h challenge sweeper.
- `backend/apps/core/tests_passkey.py` — test coverage for the management endpoints + cleanup task.
- `frontend/src/app/core/services/passkey.service.ts` — browser-side ceremony + (de)serialisation.
- `frontend/src/app/preferences/preferences.component.ts` — the Preferences "Passkeys" card.
- `docs/SAFE-DOCKER-REBUILD.md` — the `scripts\safe-rebuild.ps1` script that picks up `.env` changes.
