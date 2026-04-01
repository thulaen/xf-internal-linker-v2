import { HighlightPipe } from './highlight.pipe';

describe('HighlightPipe', () => {
  let pipe: HighlightPipe;
  let sanitizer: any;

  beforeEach(() => {
    sanitizer = {
      bypassSecurityTrustHtml: (val: string) => val
    };
    pipe = new HighlightPipe(sanitizer);
  });

  it('should create an instance', () => {
    expect(pipe).toBeTruthy();
  });

  it('should highlight matching text', () => {
    const text = 'This is a test sentence.';
    const anchor = 'test';
    const result = pipe.transform(text, anchor);
    expect(result).toBe('This is a <mark>test</mark> sentence.');
  });

  it('should be case-insensitive', () => {
    const text = 'This is a TEST sentence.';
    const anchor = 'test';
    const result = pipe.transform(text, anchor);
    expect(result).toBe('This is a <mark>TEST</mark> sentence.');
  });

  it('should handle special regex characters in anchor', () => {
    const text = 'This is safe (mostly).';
    const anchor = '(mostly).';
    const result = pipe.transform(text, anchor);
    expect(result).toBe('This is safe <mark>(mostly).</mark>');
  });

  it('should return escaped text if no anchor is provided', () => {
    const text = 'Safe & Sound';
    const result = pipe.transform(text, '');
    expect(result).toBe('Safe &amp; Sound');
  });

  it('should escape HTML in both text and anchor', () => {
    const text = '<b>Safe</b>';
    const anchor = 'Safe';
    const result = pipe.transform(text, anchor);
    expect(result).toBe('&lt;b&gt;<mark>Safe</mark>&lt;/b&gt;');
  });

  it('should handle null or undefined inputs safely', () => {
    expect(pipe.transform(null as any, 'test')).toBe('');
    expect(pipe.transform('test', null as any)).toBe('test');
  });
});
