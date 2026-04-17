/**
 * Phase F1 / Gaps 93 + 94 — Platform feature detection helpers.
 *
 * One module, two helpers, zero side effects:
 *
 *   hasPopoverApi(): boolean
 *     True when the browser implements the WHATWG `popover` HTML
 *     attribute (Chromium 114+, Firefox 125+, Safari 17). Components
 *     that want to use native popovers (instead of a Material menu
 *     or a CDK overlay) gate on this and fall back to the existing
 *     menu component when missing.
 *
 *   hasDialogElement(): boolean
 *     True when the browser implements the `<dialog>` element with
 *     `showModal()`. We use this on app-bootstrap to emit a console
 *     warning if it's missing — Angular Material's MatDialog does
 *     NOT use the native `<dialog>` (it uses cdk-overlay), so missing
 *     `<dialog>` doesn't break MatDialog. The check here is forward-
 *     looking so any future component that wants the native element
 *     can rely on it confidently.
 *
 * Why no polyfill bundle: the project's MatDialog is the
 * authoritative dialog primitive. Adding a `<dialog>` polyfill (e.g.
 * the GoogleChromeLabs one) would ship ~10kB of code we don't need
 * day-to-day. Instead we surface the missing-API warning so the
 * operator can update their browser if a future feature lands that
 * relies on the native element.
 */

export function hasPopoverApi(): boolean {
  if (typeof HTMLElement === 'undefined') return false;
  // Spec uses `togglePopover` and the `popover` attribute. Chrome
  // shipped both in the same release — checking one is sufficient.
  return 'popover' in HTMLElement.prototype;
}

export function hasDialogElement(): boolean {
  if (typeof HTMLElement === 'undefined') return false;
  if (typeof HTMLDialogElement === 'undefined') return false;
  // showModal is the spec-mandated method that distinguishes a true
  // implementation from the historical fake one.
  return typeof HTMLDialogElement.prototype.showModal === 'function';
}

/**
 * Best-effort runtime check. Logs a single advisory message at
 * boot if any of the surfaces we want are missing. Idempotent —
 * subsequent calls are no-ops.
 */
let _logged = false;
export function reportPlatformFeatures(): void {
  if (_logged) return;
  _logged = true;
  const missing: string[] = [];
  if (!hasPopoverApi()) missing.push('Popover API');
  if (!hasDialogElement()) missing.push('<dialog> element');
  if (missing.length === 0) return;
  // eslint-disable-next-line no-console
  console.info(
    '[xfil] Platform features missing in this browser:',
    missing.join(', '),
    '— components that opt in to these features will fall back to the Material equivalents.',
  );
}
