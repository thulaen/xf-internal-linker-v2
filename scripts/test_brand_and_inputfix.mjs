#!/usr/bin/env node
/**
 * Regression guard for the 2026-05-30 UI fix:
 *   1. Brand primary colour is GSC blue #4285f4 in the single source-of-truth
 *      token AND in both runtime defaults that must match it (frontend
 *      AppearanceService + backend DEFAULT_APPEARANCE), so the design token
 *      governs and is never silently overridden back to an old blue.
 *   2. The Material outlined-field "notch" compat shim is present in the global
 *      stylesheet, so the Tailwind border reset cannot reintroduce the stray
 *      vertical borders that sliced through every input field.
 *
 * Runs on the host (node) because the fix spans frontend .scss/.ts AND a
 * backend .py default; no single test container mounts all three trees.
 * Exit code 0 = all assertions pass (GREEN), 1 = any fail (RED).
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => readFileSync(join(ROOT, p), 'utf8');

const checks = [
  {
    name: 'theme token --color-primary is #4285f4',
    file: 'frontend/src/styles/_theme-vars.scss',
    test: (s) => /--color-primary:\s*#4285f4\b/.test(s),
  },
  {
    name: 'styles.scss carries the notched-outline compat shim',
    file: 'frontend/src/styles.scss',
    test: (s) =>
      /\.mat-mdc-notch-piece\.mdc-notched-outline__notch/.test(s) &&
      /border-left-width:\s*0\s*!important/.test(s),
  },
  {
    name: 'AppearanceService default primaryColor matches the token',
    file: 'frontend/src/app/core/services/appearance.service.ts',
    test: (s) => /primaryColor:\s*'#4285f4'/.test(s),
  },
  {
    name: 'backend DEFAULT_APPEARANCE primaryColor matches the token',
    file: 'backend/apps/core/views.py',
    test: (s) => /"primaryColor":\s*"#4285f4"/.test(s),
  },
];

let failed = 0;
for (const c of checks) {
  let ok = false;
  try {
    ok = c.test(read(c.file));
  } catch (e) {
    ok = false;
  }
  if (ok) {
    console.log(`PASS  ${c.name}`);
  } else {
    failed += 1;
    console.error(`FAIL  ${c.name}  (${c.file})`);
  }
}

if (failed > 0) {
  console.error(`\n${failed} assertion(s) failed`);
  process.exit(1);
}
console.log('\nAll brand + input-fix regression assertions passed');
