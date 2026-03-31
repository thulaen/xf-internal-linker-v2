# UI Testing

Simple version:

- Use Playwright to check the UI in a real browser.
- Use mocked tests for fast layout checks.
- Use live tests when the app is already running and you want real data.

## Where to run commands

Run these from:

```powershell
C:\Users\goldm\Dev\xf-internal-linker-v2\frontend
```

## Fast UI checks

This uses fake API replies.

Good for:

- layout changes
- button visibility
- smoke tests
- quick feedback while editing

Command:

```powershell
npm run ui:test
```

If you want to watch the browser:

```powershell
npm run ui:test:headed
```

## Live UI checks

This uses the real running app on `http://127.0.0.1:4200`.

Good for:

- checking real backend data
- seeing real permission messages
- testing actual page load behavior

Before this, make sure the app is already running.

Command:

```powershell
npm run ui:test:live
```

If you want to watch the browser:

```powershell
npm run ui:test:live:headed
```

## Save a screenshot

Default snapshot command:

```powershell
npm run ui:snap
```

Live snapshot command:

```powershell
npm run ui:snap:live
```

To choose a page and screenshot name, set these values first:

- `PLAYWRIGHT_CAPTURE_ROUTE` example: `/dashboard`
- `PLAYWRIGHT_CAPTURE_NAME` example: `dashboard-after`

Example:

```powershell
$env:PLAYWRIGHT_LIVE='1'
$env:PLAYWRIGHT_NO_WEBSERVER='1'
$env:PLAYWRIGHT_CAPTURE_ROUTE='/review'
$env:PLAYWRIGHT_CAPTURE_NAME='review-after'
npm run ui:snap:live
```

## Current live page checks

These real pages already have live smoke tests:

- Dashboard
- Review
- Jobs
- Link Health

## Where results go

Reports:

- `frontend/playwright-report/`

Screenshots, videos, traces:

- `frontend/test-results/`

## Good workflow for UI changes

1. Make the UI change.
2. Run `npm run ui:test`.
3. Run `npm run ui:test:live` if the real app is running.
4. Save a screenshot if you want proof of before/after.

## For other agents

This setup is repo-based, so other coding agents can use it too.

That includes tools like Claude or Antigravity, as long as they can:

- open this repo
- run terminal commands
- use the same npm scripts

They do not need special Codex-only browser features for this workflow.
