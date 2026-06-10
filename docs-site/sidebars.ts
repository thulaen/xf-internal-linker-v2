import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    {
      type: 'category',
      label: 'Documentation',
      items: [
        'intro',
        'tutorial-interactive',
      ],
    },
    {
      type: 'category',
      label: 'Architecture',
      collapsed: false,
      items: [
        'architecture/overview',
        'architecture/modular-monolith',
        'architecture/data-flow',
        'architecture/infrastructure',
      ],
    },
    {
      type: 'category',
      label: 'Modules',
      collapsed: false,
      items: [
        'modules/platform',
        'modules/content',
        'modules/sources',
        'modules/pipeline',
        'modules/suggestions',
        'modules/analytics',
        'modules/graph',
        'modules/operations',
        'modules/governance',
      ],
    },
    {
      type: 'category',
      label: 'Operations & Deployment',
      items: [
        'operations/deployment',
        'operations/monitoring',
        'operations/performance',
      ],
    },
    {
      type: 'category',
      label: 'Development Guide',
      items: [
        'development/coding-standards',
        'development/testing',
      ],
    },
    {
      type: 'doc',
      id: 'specs-adrs',
      label: 'Specs & ADRs',
    },
  ],
};

export default sidebars;
