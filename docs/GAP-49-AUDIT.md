# Gap 49 — `autocomplete` attribute audit

Phase E2 / Gap 49. Every `<input>` should carry an explicit `autocomplete`
attribute. Missing values force the browser to guess — a password manager
may autofill the wrong field, a screen-reader may announce the wrong role,
and iOS/Safari may refuse to fill at all.

## Reference values (WHATWG §4.10.18.7)

Category                   | Value
---------------------------|-----------------------
Auth: sign-in              | `autocomplete="username"` + `autocomplete="current-password"`
Auth: new account          | `autocomplete="username"` + `autocomplete="new-password"`
Profile: name              | `autocomplete="name"`
Profile: email             | `autocomplete="email"`
Profile: phone             | `autocomplete="tel"`
Profile: URL               | `autocomplete="url"`
Search / filter box        | `autocomplete="off"` (suppress stale history)
One-time code / OTP        | `autocomplete="one-time-code"`
Address line 1             | `autocomplete="address-line1"`
Address line 2             | `autocomplete="address-line2"`
Postcode                   | `autocomplete="postal-code"`
Country                    | `autocomplete="country-name"`
Credit card number         | `autocomplete="cc-number"`

Full reference: <https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#autofill>

## Already correct (no action)

| File | Fields |
|---|---|
| `login/login.component.html` | ✅ `autocomplete="username"` + `"current-password"` |
| `core/services/session-reauth-dialog.component.ts` | ✅ same pair |

## Audit result — all files fixed

Every `<input matInput>` / `<textarea matInput>` in every `.component.html`
file now carries an explicit `autocomplete` attribute.

| File | matInputs | All have autocomplete? |
|---|---|---|
| `login/login.component.html` | 2 | ✅ (username, current-password) |
| `core/services/session-reauth-dialog.component.ts` (template) | 2 | ✅ (username, current-password) |
| `crawler/crawler.component.html` | 4 | ✅ (off, off, off, url) |
| `graph/graph.component.html` | 3 | ✅ (all off — search boxes) |
| `review/review.component.html` | 1 | ✅ (off — search) |
| `review/suggestion-detail-dialog.component.html` | 2 | ✅ (off — anchor + notes) |
| `theme-customizer/theme-customizer.component.html` | 3 | ✅ (organization, off, off) |
| `behavioral-hubs/behavioral-hubs.component.html` | 1 | ✅ (off — hub name) |
| `settings/settings.component.html` | 91 | ✅ (bulk-applied "off") |

Total: 107 matInput elements, 107 with autocomplete. Zero unmarked.

The bulk `"off"` choice for settings is correct: an admin settings panel
is the canonical use case for suppressing browser autofill suggestions
for numeric thresholds, feature flags, api keys, and domain names —
values the browser has no business suggesting from stored user data.

## Default rule of thumb

If a field is **not** identity/profile/address, use `autocomplete="off"`.
Browsers honour `"off"` weakly (Chrome will still offer stored values if
the input looks strongly like a known form field) but it improves
accessibility announcements and prevents password managers from
mis-filling random text boxes.

## Verification

Regex-check the codebase for `matInput` elements without `autocomplete=`:

```python
import re
from pathlib import Path

pattern = re.compile(
    r'<(?:input|textarea)\b[^>]*?\bmatInput\b[^>]*?>',
    re.DOTALL,
)
missing = 0
for f in Path('frontend/src/app').rglob('*.html'):
    html = f.read_text(encoding='utf-8')
    for m in pattern.findall(html):
        if 'autocomplete=' not in m:
            print(f"{f}: missing — {m[:80]}...")
            missing += 1
assert missing == 0, f"{missing} matInputs lack autocomplete"
```

Expected output: empty. Any hit is a new regression and must be fixed before merge.
