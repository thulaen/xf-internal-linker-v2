/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: 'no-circular',
      severity: 'error',
      comment: 'Circular dependencies cause hard-to-debug issues and confuse AI agents.',
      from: {},
      to: {
        circular: true,
      },
    },
    {
      name: 'no-orphans',
      severity: 'warn',
      comment: 'Orphaned modules are likely dead code left behind by refactors.',
      from: {
        orphan: true,
        pathNot: [
          '\\.spec\\.(ts|js)$',
          '(^|/)index\\.(ts|js)$',
          '\\.d\\.ts$',
          '(^|/)karma\\.conf',
          '(^|/)[\\.]*rc\\.',
        ],
      },
      to: {},
    },
    {
      name: 'services-not-in-components',
      severity: 'warn',
      comment: 'Components should not be imported by services — only the other way around.',
      from: {
        path: '\\.service\\.ts$',
      },
      to: {
        path: '\\.component\\.ts$',
      },
    },
  ],
  options: {
    doNotFollow: {
      path: 'node_modules',
    },
    tsPreCompilationDeps: true,
    tsConfig: {
      fileName: './tsconfig.json',
    },
    reporterOptions: {
      dot: {
        collapsePattern: 'node_modules/[^/]+',
      },
    },
  },
};
