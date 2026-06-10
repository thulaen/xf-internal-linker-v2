import {
  token,
  clearTokenCache,
  withAlpha,
  gscChartBase,
  gscPalette,
} from './echarts-theme';

describe('echarts-theme helpers', () => {
  beforeEach(() => {
    // Ensure clean slate before each test
    clearTokenCache();
  });

  afterEach(() => {
    // Clean up any styles applied to the document
    document.documentElement.style.removeProperty('--test-mock-token');
    document.documentElement.style.removeProperty('--color-primary');
    document.documentElement.style.removeProperty('--series-indexed');
    clearTokenCache();
  });

  describe('token()', () => {
    it('should read a token from the DOM if present', () => {
      document.documentElement.style.setProperty('--test-mock-token', '#abcdef');
      expect(token('--test-mock-token')).toBe('#abcdef');
    });

    it('should fall back to TOKEN_FALLBACKS if token is missing from DOM', () => {
      // Ensure it is not set.
      document.documentElement.style.removeProperty('--color-primary');
      expect(token('--color-primary')).toBe('#4285f4');
    });

    it('should fall back to default grey (#80868b) for unknown tokens missing from both DOM and FALLBACKS', () => {
      expect(token('--unknown-missing-token')).toBe('#80868b');
    });

    it('should cache resolved values', () => {
      document.documentElement.style.setProperty('--test-mock-token', '#111111');
      expect(token('--test-mock-token')).toBe('#111111'); // Reads from DOM and caches

      // Modify the DOM value
      document.documentElement.style.setProperty('--test-mock-token', '#222222');
      // Should still return the cached value
      expect(token('--test-mock-token')).toBe('#111111');
    });

    it('should gracefully handle empty string values from DOM and use fallback', () => {
      document.documentElement.style.setProperty('--color-primary', '   '); // spaces which trim() to empty
      expect(token('--color-primary')).toBe('#4285f4');
    });
  });

  describe('clearTokenCache()', () => {
    it('should clear the token cache and allow re-reading from DOM', () => {
      document.documentElement.style.setProperty('--test-mock-token', '#111111');
      expect(token('--test-mock-token')).toBe('#111111');

      // Modify the DOM value
      document.documentElement.style.setProperty('--test-mock-token', '#222222');
      clearTokenCache(); // Invalidate cache

      // Should now return the updated DOM value
      expect(token('--test-mock-token')).toBe('#222222');
    });
  });

  describe('withAlpha()', () => {
    it('should convert standard 6-character hex (with #) to rgba', () => {
      expect(withAlpha('#ffffff', 0.5)).toBe('rgba(255, 255, 255, 0.5)');
      expect(withAlpha('#000000', 1)).toBe('rgba(0, 0, 0, 1)');
      expect(withAlpha('#4285f4', 0.1)).toBe('rgba(66, 133, 244, 0.1)');
    });

    it('should convert 6-character hex (without #) to rgba', () => {
      expect(withAlpha('ffffff', 0.75)).toBe('rgba(255, 255, 255, 0.75)');
      expect(withAlpha('4285f4', 0.2)).toBe('rgba(66, 133, 244, 0.2)');
    });

    it('should return the original string if it is not 6 characters after removing #', () => {
      expect(withAlpha('#fff', 0.5)).toBe('#fff'); // 3-char hex
      expect(withAlpha('#1234567', 0.5)).toBe('#1234567'); // Too long
      expect(withAlpha('red', 0.5)).toBe('red'); // Non-hex word
      expect(withAlpha('', 0.5)).toBe(''); // Empty string
    });
    
    it('should parse valid hex values correctly across ranges', () => {
      // Boundary values
      expect(withAlpha('#010203', 0)).toBe('rgba(1, 2, 3, 0)');
      expect(withAlpha('#fefdfc', 0.99)).toBe('rgba(254, 253, 252, 0.99)');
    });
  });

  describe('gscChartBase()', () => {
    it('should return a well-formed ECharts option base', () => {
      const base = gscChartBase() as any;
      
      expect(base.textStyle).toBeDefined();
      expect(base.textStyle.fontFamily).toContain('-apple-system');
      // Should use --color-text-secondary token
      expect(base.textStyle.color).toBe(token('--color-text-secondary'));

      expect(base.tooltip).toBeDefined();
      expect(base.tooltip.backgroundColor).toBe('rgba(32, 33, 36, 0.92)');

      expect(base.legend).toBeDefined();
      expect(base.legend.bottom).toBe(0);

      expect(base.grid).toBeDefined();
      expect(base.grid.containLabel).toBeTrue();

      expect(base._gridFaint).toBe(withAlpha(token('--color-text-muted'), 0.1));
    });
  });

  describe('gscPalette()', () => {
    it('should return an array of exactly 6 color strings', () => {
      const palette = gscPalette();
      expect(Array.isArray(palette)).toBeTrue();
      expect(palette.length).toBe(6);
    });

    it('should resolve to the correct fallback tokens when no DOM values are present', () => {
      // Note: TOKEN_FALLBACKS values from source
      const expectedFallbacks = [
        '#4285f4', // --color-primary
        '#00897b', // --series-indexed
        '#fbbc04', // --color-warning-accent
        '#e81403', // --color-error
        '#5e35b1', // --series-impressions
        '#80868b', // --series-not-indexed
      ];
      expect(gscPalette()).toEqual(expectedFallbacks);
    });
    
    it('should reflect dynamically updated DOM tokens', () => {
      document.documentElement.style.setProperty('--color-primary', '#111111');
      document.documentElement.style.setProperty('--series-indexed', '#222222');
      
      const palette = gscPalette();
      expect(palette[0]).toBe('#111111');
      expect(palette[1]).toBe('#222222');
    });
  });
});
