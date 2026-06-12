// Vitest test setup. The production app runs zoneless
// (provideZonelessChangeDetection), but the existing specs were written for the
// Karma + zone.js environment and 57 of them use Angular's zone-based
// `fakeAsync` / `tick` helpers. Loading zone.js + zone.js/testing here
// reproduces that environment so those specs keep working under Vitest.
import 'zone.js';
import 'zone.js/testing';
import { vi } from 'vitest';

// ── fakeAsync support for Vitest ─────────────────────────────────────────────
// zone.js 0.15 ships only jasmine-patch and mocha-patch — there is no Vitest
// patch — so Angular's `fakeAsync`/`tick` have no ProxyZone to run in and throw
// "Expected to be running in 'ProxyZone'". This replicates mocha-patch's
// behaviour for Vitest: it wraps the describe/it/beforeEach/afterEach callbacks
// so each runs inside a Zone ProxyZone. Modelled on
// node_modules/zone.js/fesm2015/mocha-patch.js.
{
  const Zn = (globalThis as unknown as { Zone?: any }).Zone;
  const ProxyZoneSpec = Zn?.['ProxyZoneSpec'];
  const SyncTestZoneSpec = Zn?.['SyncTestZoneSpec'];
  if (Zn && ProxyZoneSpec && SyncTestZoneSpec) {
    const rootZone = Zn.current;
    const syncZone = rootZone.fork(new SyncTestZoneSpec('vitest.describe'));
    const proxyZone = rootZone.fork(new ProxyZoneSpec());
    const gt = globalThis as unknown as Record<string, any>;

    const inZone =
      (zone: any) =>
      (fn: any) =>
        typeof fn === 'function'
          ? function (this: unknown, ...args: unknown[]) {
              return zone.run(fn, this, args);
            }
          : fn;

    // Wrap the function arguments of a test global so the callback runs in
    // `zone`; non-function args (name, timeout) pass through unchanged.
    const wrapGlobal = (name: string, zone: any) => {
      const orig = gt[name];
      if (typeof orig !== 'function') return;
      const wrapFn = inZone(zone);
      const make =
        (target: any) =>
        function (this: unknown, ...args: any[]) {
          return target.apply(
            this,
            args.map((a) => (typeof a === 'function' ? wrapFn(a) : a)),
          );
        };
      const patched: any = make(orig);
      // Preserve and re-wrap the common chainables so their callbacks are
      // zoned too (it.only / it.skip / test.only / test.skip).
      for (const key of ['only', 'skip', 'todo', 'concurrent', 'sequential']) {
        if (typeof orig[key] === 'function') {
          patched[key] = make(orig[key]);
        }
      }
      // Copy anything else (each, extend, runIf, …) by reference.
      for (const key of Object.keys(orig)) {
        if (!(key in patched)) patched[key] = orig[key];
      }
      gt[name] = patched;
    };

    wrapGlobal('it', proxyZone);
    wrapGlobal('test', proxyZone);
    wrapGlobal('beforeEach', proxyZone);
    wrapGlobal('afterEach', proxyZone);
    wrapGlobal('describe', syncZone);
  }
}

// Jasmine-parity `createSpyObj`, registered globally so the migrated specs need
// no per-file import. Builds an object whose named methods are Vitest mocks.
// Typed by src/testing/spy.global.d.ts.
(globalThis as unknown as { createSpyObj: unknown }).createSpyObj = (
  methodNames: readonly string[],
  properties?: Record<string, unknown>,
): Record<string, unknown> => {
  const obj: Record<string, unknown> = {};
  for (const name of methodNames) {
    obj[name] = vi.fn();
  }
  if (properties) {
    Object.assign(obj, properties);
  }
  return obj;
};

// ── jsdom polyfills ──────────────────────────────────────────────────────────
// jsdom (Vitest's DOM) does not implement several browser APIs that the old
// Karma + ChromeHeadless environment provided. The specs were written against
// those APIs, so we stub them here. No-op stubs are enough — the specs assert
// on component behaviour, not on the browser's native rendering.
type AnyFn = (...args: unknown[]) => unknown;
const g = globalThis as unknown as Record<string, unknown>;

class StubObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): unknown[] {
    return [];
  }
}
if (!('IntersectionObserver' in g)) {
  g['IntersectionObserver'] = StubObserver;
}
if (!('ResizeObserver' in g)) {
  g['ResizeObserver'] = StubObserver;
}

if (typeof Element !== 'undefined') {
  Element.prototype.scrollIntoView ??= function scrollIntoView(): void {};
  Element.prototype.scrollTo ??= function scrollTo(): void {};
}

if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

// Canvas 2D context for ECharts (canvas renderer). jsdom returns null from
// getContext, which makes ECharts crash on clearRect. Return a no-op context
// with every method ECharts touches.
if (typeof HTMLCanvasElement !== 'undefined') {
  const noop: AnyFn = () => undefined;
  const ctx2d = new Proxy(
    {
      measureText: () => ({ width: 0 }),
      getImageData: (_x: number, _y: number, w: number, h: number) => ({
        data: new Uint8ClampedArray(Math.max(0, w) * Math.max(0, h) * 4),
      }),
      createImageData: (w: number, h: number) => ({
        data: new Uint8ClampedArray(Math.max(0, w) * Math.max(0, h) * 4),
      }),
      createLinearGradient: () => ({ addColorStop: noop }),
      createRadialGradient: () => ({ addColorStop: noop }),
      createPattern: () => null,
      canvas: null as unknown,
    },
    { get: (target, prop) => (prop in target ? (target as Record<string | symbol, unknown>)[prop] : noop) },
  );
  HTMLCanvasElement.prototype.getContext = function getContext(): unknown {
    return ctx2d;
  } as typeof HTMLCanvasElement.prototype.getContext;
}

// WebAuthn — the passkey specs assume a credential-capable browser (the old
// ChromeHeadless shipped PublicKeyCredential + navigator.credentials).
if (typeof window !== 'undefined' && !('PublicKeyCredential' in window)) {
  (window as unknown as Record<string, unknown>)['PublicKeyCredential'] = class PublicKeyCredential {};
}
if (typeof navigator !== 'undefined' && !('credentials' in navigator)) {
  (navigator as unknown as Record<string, unknown>)['credentials'] = {
    create: () => Promise.resolve(null),
    get: () => Promise.resolve(null),
  };
}

// Blob-URL helpers used by CSV/file export buttons.
URL.createObjectURL ??= (() => 'blob:mock') as typeof URL.createObjectURL;
URL.revokeObjectURL ??= (() => undefined) as typeof URL.revokeObjectURL;

// Clipboard — jsdom has no navigator.clipboard; copy-link buttons spy on it.
if (typeof navigator !== 'undefined' && !navigator.clipboard) {
  (navigator as unknown as Record<string, unknown>)['clipboard'] = {
    writeText: () => Promise.resolve(),
    readText: () => Promise.resolve(''),
  };
}
