import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'XF Internal Linker',
  tagline: 'Intelligent Internal Linking Engine',
  favicon: 'img/favicon.ico',

  url: 'http://docs.localhost',
  baseUrl: '/',

  organizationName: 'xf-internal-linker',
  projectName: 'docs',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  markdown: {
    mermaid: true,
  },

  themes: ['@docusaurus/theme-mermaid'],
  plugins: [
    ['docusaurus-lunr-search', {
      disableVersioning: true,
    }],
    async function myPlugin(context, options) {
      return {
        name: "docusaurus-tailwindcss",
        configurePostCss(postcssOptions) {
          // Appends Tailwind v4 postcss plugin
          postcssOptions.plugins.push(require("@tailwindcss/postcss"));
          return postcssOptions;
        },
      };
    },
  ],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          routeBasePath: '/', // Serve docs at root
        },
        blog: false, // Disable blog
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      defaultMode: 'light',
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'XF Internal Linker',
      logo: {
        alt: 'XF Internal Linker Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Documentation',
        },
      ],
    },
    footer: {
      style: 'light',
      links: [
        {
          title: 'Documentation',
          items: [
            {
              label: 'Getting Started',
              to: '/intro',
            },
            {
              label: 'Architecture',
              to: '/architecture/overview',
            },
          ],
        },
        {
          title: 'Modules',
          items: [
            {
              label: 'Platform',
              to: '/modules/platform',
            },
            {
              label: 'Pipeline',
              to: '/modules/pipeline',
            },
          ],
        },
        {
          title: 'Reference',
          items: [
            {
              label: 'Specs & ADRs',
              to: '/specs-adrs',
            },
            {
              label: 'Operations',
              to: '/operations/deployment',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} XF Internal Linker. Apple Liquid Glass Aesthetic.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'rust', 'typescript'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
