#!/usr/bin/env node
// node-browser runner launcher (ADR 0010, KUBE PLAN SLICE-23).
//
// Runs one frontend dev tool (vitest, stryker, eslint, tsc, ...) from the baked
// node_modules. It lives in frontend/ on purpose: in the js_binary runfiles tree
// it ends up beside node_modules, which is what lets Node's module resolution use
// the rules_js symlink store (the same layout pnpm uses). rules_js does not
// materialise node_modules/.bin, so we resolve each tool through its package's
// "bin" field instead. Usage in-image:  <entrypoint> vitest run  |  eslint .
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);

// Tools whose CLI name differs from their npm package name.
const PACKAGE_ALIASES = {
  stryker: ["@stryker-mutator/core"],
  tsc: ["typescript"],
  ng: ["@angular/cli"],
};

function resolveBin(tool) {
  for (const pkg of [tool, ...(PACKAGE_ALIASES[tool] ?? [])]) {
    let metaPath;
    try {
      metaPath = require.resolve(`${pkg}/package.json`);
    } catch {
      continue;
    }
    const bin = JSON.parse(readFileSync(metaPath, "utf8")).bin;
    const rel =
      typeof bin === "string" ? bin : bin?.[tool] ?? Object.values(bin ?? {})[0];
    if (rel) return join(dirname(metaPath), rel);
  }
  return null;
}

const [tool, ...rest] = process.argv.slice(2);
if (!tool) {
  console.error("usage: <tool> [args...]   e.g.  vitest run   |   eslint .");
  process.exit(2);
}

const bin = resolveBin(tool);
if (!bin) {
  console.error(`tool not found in node_modules: ${tool}`);
  process.exit(127);
}

const result = spawnSync(process.execPath, [bin, ...rest], { stdio: "inherit" });
process.exit(result.status ?? 1);
