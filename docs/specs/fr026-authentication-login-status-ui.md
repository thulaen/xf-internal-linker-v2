# FR-026 - Authentication & Login Status UI

## Confirmation

- `FR-026` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 29`.
- This spec is written before implementation because the user explicitly requested the build blueprint in advance.
- Repo confirmed:
  - the backend already has `SessionAuthentication` and `TokenAuthentication` configured;
  - `rest_framework.permissions.IsAuthenticated` is the default permission class — all endpoints require auth except `/api/settings/appearance/` and `/api/dashboard/`;
  - DRF's built-in login and logout views are already registered at `/api/auth/login/` and `/api/auth/logout/`;
  - `rest_framework.authtoken` is installed — `Token` model and `obtain_auth_token` endpoint are available;
  - the Angular auth interceptor (`core/interceptors/auth.interceptor.ts`) is a stub — it does nothing;
  - the Angular route guards are commented out and never applied;
  - there is no Angular login page, no auth service, no token storage, and no user display in the shell today.

## Scope Statement

This FR completes the "Phase 4" auth work noted in the frontend stubs and adds a login status indicator to the toolbar.

| Part | What it does |
|---|---|
| 1. `/api/auth/me/` endpoint | Returns the logged-in user's username and basic info |
| 2. Auth service | Angular service that stores token, checks login state, exposes current user |
| 3. Auth interceptor | Attaches token to every API request |
| 4. Login page | Simple username + password form at `/login` |
| 5. Auth guard | Redirects unauthenticated users to `/login` |
| 6. Login status in toolbar | Username + logout button shown in the shell when logged in |

**Hard boundaries:**

- This FR does not add roles, permissions, or multi-user management.
- This FR does not change backend permission logic — `IsAuthenticated` remains the default.
- This FR does not add OAuth, SSO, or third-party login.
- This FR does not change any existing API endpoint behaviour.

## Current Repo Map

### Backend

- `backend/config/settings/base.py`
  - `DEFAULT_AUTHENTICATION_CLASSES`: `SessionAuthentication`, `TokenAuthentication`.
  - `DEFAULT_PERMISSION_CLASSES`: `IsAuthenticated`.
  - `rest_framework.authtoken` in `INSTALLED_APPS`.
- `backend/config/urls.py`
  - `path("api/auth/", include("rest_framework.urls"))` — DRF login/logout views.
  - No custom `/api/auth/me/` endpoint exists yet.
- `backend/apps/core/views.py`
  - No user-info endpoint.

### Frontend stubs (to be completed by this FR)

- `frontend/src/app/core/interceptors/auth.interceptor.ts`
  - Currently does nothing. Comment: "Phase 4: attach auth token / CSRF token here."
- `frontend/src/app/app.routes.ts`
  - No guards applied. Comment: "Auth guard protects all routes except login (added in Phase 4)."
- `frontend/src/app/app.component.ts`
  - No auth state. No user display. No logout button.

## Workflow Drift / Doc Mismatch Found During Inspection

- `docs/v2-master-plan.md` references auth as a Phase 4 item. The backend completed its part; the frontend was never finished. This FR closes the gap.
- `/api/settings/appearance/` and `/api/dashboard/` are intentionally public (`AllowAny`). The login page must NOT require auth to load the app theme/appearance. This is already handled — no change needed.
- The DRF browsable API login form at `/api/auth/login/` uses session auth. This FR uses token auth for the Angular app. Both coexist — no conflict.

## Problem Definition

Simple version first.

The app requires a login but has never shown the user whether they are logged in or not. The Angular frontend sends requests to protected endpoints with no credentials, which silently fails. There is no login page to get credentials, no way to see who is logged in, and no logout button.

This FR adds the complete login flow and a clear status indicator in the top toolbar.

---

## Part 1 — `/api/auth/me/` Endpoint

### Why this is needed

The Angular app needs a way to check: "am I currently logged in, and if so, who am I?" DRF's built-in views do not provide this.

### Implementation

Add to `backend/apps/core/views.py`:

```python
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email,
            "is_staff": request.user.is_staff,
            "date_joined": request.user.date_joined,
        })
```

Add to URL config:

```
GET /api/auth/me/
```

Response when authenticated:

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "is_staff": true,
  "date_joined": "2026-03-23T10:00:00Z"
}
```

Returns `401 Unauthorized` when not authenticated.

### Token obtain endpoint

DRF's `obtain_auth_token` view is already available. Register it explicitly:

```
POST /api/auth/token/
```

Request body: `{ "username": "...", "password": "..." }`
Response: `{ "token": "abc123..." }`

This is what the Angular login form calls.

---

## Part 2 — Angular Auth Service

Add: `frontend/src/app/core/services/auth.service.ts`

### Responsibilities

- Call `POST /api/auth/token/` with credentials; store the returned token in `localStorage`.
- Call `GET /api/auth/me/` to load current user info.
- Expose `isLoggedIn$` (Observable<boolean>) and `currentUser$` (Observable<User | null>).
- Provide `login(username, password)` and `logout()` methods.
- On app startup: check `localStorage` for an existing token; if found, call `/api/auth/me/` to verify it is still valid.

### Token storage

Store in `localStorage` under key `xfil_auth_token`.

On logout: remove the key and clear `currentUser$`.

### User model

```typescript
export interface AuthUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  date_joined: string;
}
```

---

## Part 3 — Auth Interceptor

Complete the existing stub at:
`frontend/src/app/core/interceptors/auth.interceptor.ts`

### Behaviour

- On every outgoing HTTP request: read `xfil_auth_token` from `localStorage`.
- If token exists: add `Authorization: Token <token>` header.
- If request returns `401`: call `authService.logout()` and redirect to `/login`.

### Exceptions

Do not add the auth header to:
- `POST /api/auth/token/` — this is the login call itself; it has no token yet.

---

## Part 4 — Login Page

Add route: `/login`

Add component: `frontend/src/app/login/login.component.ts`

### UI

- App logo (reuses existing logo from appearance settings).
- "Sign in" heading.
- Username field.
- Password field.
- "Sign in" button.
- Error message area: "Invalid username or password." shown on 400/401 response.
- Loading spinner on the button while the request is in flight.

### Behaviour

1. On submit: call `authService.login(username, password)`.
2. On success: redirect to the route the user originally tried to visit (or `/` if none).
3. On failure: show error message. Do not clear the username field.

### No public registration

There is no "create account" link. This is an internal single-operator tool. Accounts are created via Django admin only.

---

## Part 5 — Auth Guard

Complete the existing stub referenced in `app.routes.ts`.

Add: `frontend/src/app/core/guards/auth.guard.ts`

### Behaviour

- Applied to all routes except `/login`.
- If `authService.isLoggedIn$` is `false`: redirect to `/login` and preserve the attempted URL as a query param (`?returnUrl=/settings`).
- If `true`: allow navigation.

---

## Part 6 — Login Status in Toolbar

Update:
- `frontend/src/app/app.component.html`
- `frontend/src/app/app.component.ts`

### When logged in

Show in the top-right of the toolbar:

```
[person icon]  admin          [logout icon button]
```

- Username is read from `authService.currentUser$`.
- Logout button calls `authService.logout()` then navigates to `/login`.

### When not logged in

The toolbar is not shown — the login page has its own minimal layout without the main shell.

### Tooltip

Hovering the username shows: "Signed in as admin — click to sign out" (or a dedicated logout button with its own label).

---

## Settings UI

No new settings card needed. Authentication is a system-level concern, not an operator preference.

If wanted in future: an "Active session" indicator could be added to the FR-022 health dashboard as a read-only status row. That is out of scope here.

---

## Test Plan

### Backend tests

- `GET /api/auth/me/` with valid token returns correct user fields.
- `GET /api/auth/me/` with no token returns `401`.
- `POST /api/auth/token/` with valid credentials returns a token.
- `POST /api/auth/token/` with wrong password returns `400`.

### Frontend tests

- `AuthService.login()` stores token in `localStorage` on success.
- `AuthService.login()` does not store token on failure.
- `AuthService.logout()` removes token and clears `currentUser$`.
- Auth interceptor attaches `Authorization: Token ...` header to protected requests.
- Auth interceptor does NOT attach header to the token endpoint.
- Auth guard redirects to `/login` when not authenticated.
- Auth guard allows navigation when authenticated.
- Login form shows error message on bad credentials.
- Toolbar shows username when logged in.

### Manual verification

- Open the app with no token stored → redirected to `/login`.
- Enter wrong password → error message shown.
- Enter correct credentials → redirected to dashboard, username visible in toolbar.
- Click logout → redirected to `/login`, token cleared.
- Open the app with a valid token already in `localStorage` → logged straight in, no redirect.
- Open the app with an expired/invalid token in `localStorage` → redirected to `/login`.

---

## Dependencies

- No other FR dependencies.
- Should be implemented before any FR that requires a logged-in user context in the UI.

---

## Acceptance Criteria

- Opening the app without credentials redirects to a login page.
- Logging in with correct credentials stores a token and enters the app.
- The toolbar shows the current username and a logout button when logged in.
- Logging out clears the token and returns to the login page.
- All protected API calls include the auth token automatically.
- A `401` response from any endpoint logs the user out and returns them to `/login`.
- `GET /api/auth/me/` returns the current user's username and basic info.

## Out-of-Scope Follow-Up

- Multi-user management (add/remove users from the UI).
- Role-based access control.
- OAuth / SSO / social login.
- Password reset flow.
- Remember-me / refresh tokens.
- Session timeout warnings.
- "Active session" health card in FR-022.
