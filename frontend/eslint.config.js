// @ts-check
const eslint = require("@eslint/js");
const tseslint = require("typescript-eslint");
const angular = require("angular-eslint");

module.exports = tseslint.config(
  {
    files: ["**/*.ts"],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommended,
      ...angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      "@angular-eslint/directive-selector": [
        "error",
        {
          type: "attribute",
          prefix: "app",
          style: "camelCase",
        },
      ],
      "@angular-eslint/component-selector": [
        "error",
        {
          type: "element",
          prefix: "app",
          style: "kebab-case",
        },
      ],
      // Promoted from "off" → "warn" on 2026-05-09 (AutoIssue #21).
      // 9 site-level any annotations were replaced with proper types in the
      // same change; warn is enough to surface regressions in PRs without
      // breaking CI for the 0-3 acceptable third-party-typing escape hatches.
      // Promote to "error" once the bundle is fully `any`-free for two
      // consecutive sessions.
      "@typescript-eslint/no-explicit-any": "warn",
      "@angular-eslint/prefer-inject": "off",
    },
  },
  {
    files: ["**/*.html"],
    extends: [
      ...angular.configs.templateRecommended,
      ...angular.configs.templateAccessibility,
    ],
    rules: {
      // Major template migration (*ngIf → @if) — separate task
      "@angular-eslint/template/prefer-control-flow": "off",
      // Accessibility — warn for now, enforce later
      "@angular-eslint/template/label-has-associated-control": "warn",
      "@angular-eslint/template/click-events-have-key-events": "warn",
      "@angular-eslint/template/interactive-supports-focus": "warn",
    },
  }
);
