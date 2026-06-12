module.exports = function (config) {
  config.set({
    basePath: '',
    frameworks: ['parallel', 'jasmine', '@angular-devkit/build-angular'],
    plugins: [
      require('karma-parallel'),
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
    ],
    // ng test parallelism — karma-parallel shards specs across N headless-Chrome
    // executors so the suite uses multiple cores. run-angular-quality.sh sets
    // KARMA_PARALLEL_EXECUTORS to the Dell core budget (capped at 16); locally it
    // falls back to 4. Set KARMA_PARALLEL_EXECUTORS=1 to disable sharding.
    parallelOptions: {
      executors: Number(process.env.KARMA_PARALLEL_EXECUTORS) || 4,
      shardStrategy: 'round-robin',
    },
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
      // Whole-repo coverage is reported here, but the Docker quality scripts
      // decide whether it is a touched-file blocker or quality debt.
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
