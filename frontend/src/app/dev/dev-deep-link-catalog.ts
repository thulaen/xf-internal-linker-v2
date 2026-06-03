import type { DeepLinkEntry } from '../core/routing/deep-link-catalog';

export const DEV_DEEP_LINK_CATALOG: readonly DeepLinkEntry[] = [
  {
    key: 'dev.error-generator',
    label: 'Faro error generator',
    subtitle: 'Hidden development-only page that emits browser errors for Faro picker checks.',
    route: '/dev/error-generator',
    searchTerms: ['dev', 'faro', 'browser errors', 'web vitals', 'layout shift'],
  },
];
