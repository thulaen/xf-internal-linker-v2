/**
 * query-state — two-way bind component filter/sort/page state to the URL.
 *
 * Phase U2 / Gap 17.
 *
 * Currently several list pages (Analytics, Settings, Link Health) track
 * their filter + sort + pagination in component properties only — which
 * means the back button loses the filter, the URL isn't bookmarkable,
 * and "Share this view" is impossible. This helper is the one place
 * that pattern gets fixed.
 *
 * Public API:
 *   - `readQueryState(route, schema)` — parse the current `?q=...&sort=...`
 *     into a typed object using a per-field schema that coerces strings.
 *   - `writeQueryState(router, route, state)` — push `state` into the URL
 *     via `router.navigate([], { queryParams, queryParamsHandling: 'merge' })`.
 *   - `QueryStateFields` — type-safe field schema (string | number | bool | array).
 *
 * Why not a full-fat `@angular/cdk/query-params` thing: the feature is
 * tiny (~80 LOC), the callers are a dozen list pages, and inlining a
 * typed reader/writer means existing services don't need a refactor.
 *
 * Example:
 *   // In a component:
 *   interface Filters {
 *     q: string;
 *     sort: 'date' | 'score';
 *     page: number;
 *     showArchived: boolean;
 *   }
 *
 *   private readonly schema: QueryStateFields<Filters> = {
 *     q: { type: 'string',  default: '' },
 *     sort: { type: 'string', default: 'date', allowed: ['date', 'score'] },
 *     page: { type: 'number', default: 1 },
 *     showArchived: { type: 'bool', default: false },
 *   };
 *
 *   filters = readQueryState(this.route, this.schema);
 *
 *   onFilterChange(next: Filters): void {
 *     this.filters = next;
 *     writeQueryState(this.router, this.route, next, this.schema);
 *   }
 */

import { ActivatedRoute, Router } from '@angular/router';

// ─────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────

type PrimitiveKind = 'string' | 'number' | 'bool' | 'array';

interface BaseField<T> {
  type: PrimitiveKind;
  /** Returned when the URL has no value / an invalid value. */
  default: T;
  /** Optional whitelist — values not in the list fall back to default. */
  allowed?: readonly T[];
}

export type QueryStateFields<TState> = {
  [K in keyof TState]: BaseField<TState[K]>;
};

// ─────────────────────────────────────────────────────────────────────
// Read
// ─────────────────────────────────────────────────────────────────────

/**
 * Parse the current route's query params into a typed state object.
 *
 * - Missing fields fall back to `schema[k].default`.
 * - Invalid types (e.g. `?page=abc`) fall back to `default`.
 * - Whitelist violations fall back to `default`.
 * - Array fields accept comma-separated values (`?tags=a,b,c`).
 */
export function readQueryState<TState extends object>(
  route: ActivatedRoute,
  schema: QueryStateFields<TState>,
): TState {
  const raw = route.snapshot.queryParamMap;
  const out: Partial<TState> = {};

  for (const key of Object.keys(schema) as (keyof TState)[]) {
    const field = schema[key];
    const stringValue = raw.get(String(key));
    out[key] = coerce(stringValue, field) as TState[typeof key];
  }

  return out as TState;
}

function coerce<T>(raw: string | null, field: BaseField<T>): T {
  if (raw === null || raw === '') return field.default;
  let value: unknown;
  switch (field.type) {
    case 'number': {
      const n = Number(raw);
      value = Number.isFinite(n) ? n : field.default;
      break;
    }
    case 'bool': {
      value = raw === 'true' ? true : raw === 'false' ? false : field.default;
      break;
    }
    case 'array': {
      value = raw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      break;
    }
    case 'string':
    default: {
      value = raw;
      break;
    }
  }

  if (field.allowed && !field.allowed.includes(value as T)) {
    return field.default;
  }
  return value as T;
}

// ─────────────────────────────────────────────────────────────────────
// Write
// ─────────────────────────────────────────────────────────────────────

/**
 * Push the given state into the URL via `router.navigate`.
 *
 * Behaviour:
 *   - Uses `queryParamsHandling: 'merge'` so unrelated params (e.g. a
 *     `?returnUrl=` sitting alongside filters) are preserved.
 *   - Fields at their default value are WRITTEN AS NULL so the URL
 *     stays short: `?q=foo` instead of `?q=foo&sort=date&page=1`.
 *   - Arrays serialise as comma-separated values.
 *   - Uses `replaceUrl: true` so rapid typing (e.g. a search box) does
 *     not pollute browser history with hundreds of back-button entries.
 */
export function writeQueryState<TState extends object>(
  router: Router,
  route: ActivatedRoute,
  state: TState,
  schema: QueryStateFields<TState>,
): Promise<boolean> {
  const queryParams: Record<string, string | null> = {};
  for (const key of Object.keys(schema) as (keyof TState)[]) {
    const field = schema[key];
    const value = state[key];
    const serialised = serialise(value, field);
    queryParams[String(key)] = serialised;
  }

  return router.navigate([], {
    relativeTo: route,
    queryParams,
    queryParamsHandling: 'merge',
    replaceUrl: true,
  });
}

function serialise<T>(value: T, field: BaseField<T>): string | null {
  // At-default values become `null` so navigation removes them from the URL.
  if (areEqual(value, field.default)) return null;

  switch (field.type) {
    case 'array':
      if (Array.isArray(value)) return value.length === 0 ? null : value.join(',');
      return null;
    case 'bool':
      return value ? 'true' : 'false';
    case 'number':
      return typeof value === 'number' && Number.isFinite(value) ? String(value) : null;
    case 'string':
    default:
      if (value === '' || value === undefined || value === null) return null;
      return String(value);
  }
}

function areEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((v, i) => v === b[i]);
  }
  return false;
}
