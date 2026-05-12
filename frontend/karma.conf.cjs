module.exports = function (config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine', '@angular-devkit/build-angular'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
    ],
    client: {
      jasmine: {
        // Randomize spec execution order — surfaces tests that only pass
        // because of the order they ran in. seed:null lets Jasmine generate
        // a fresh seed per run (printed in the output so failures repro).
        random: true,
        seed: null,
        failSpecWithNoExpectations: true,
      },
      clearContext: false,
    },
    coverageReporter: {
      dir: require('path').join(__dirname, './coverage/xf-internal-linker-frontend'),
      subdir: '.',
      // `json-summary` writes coverage-summary.json (per-file totals)
      // which the Phase-3 FR-251 Gap #3 ratchet (.coverage-baseline.json
      // — file `frontend.json` form) parses to enforce per-file floors.
      // The text-summary + html outputs are unchanged for human use.
      reporters: [
        { type: 'html' },
        { type: 'text-summary' },
        { type: 'json-summary' },
        { type: 'lcovonly' },
      ],
      thresholds: {
        statements: 30,
        branches: 25,
        functions: 30,
        lines: 30,
      },
    },
    reporters: ['progress'],
    browsers: ['ChromeHeadless'],
    customLaunchers: {
      ChromeHeadlessNoSandbox: {
        base: 'ChromeHeadless',
        flags: [
          '--no-sandbox',
          '--disable-dev-shm-usage',
          '--disable-gpu',
          '--disable-software-rasterizer',
        ],
      },
    },
    restartOnFileChange: true,
  });
};
