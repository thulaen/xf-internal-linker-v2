import { escapeHtml, highlightText } from './highlight.utils';

describe('highlight utils', () => {
  it('escapes HTML metacharacters before rendering text', () => {
    expect(escapeHtml(`<script>alert("x")</script>'&`)).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;&#039;&amp;'
    );
  });

  it('wraps case-insensitive anchor matches in mark tags', () => {
    expect(highlightText('Alpha beta ALPHA', 'alpha')).toBe(
      '<mark>Alpha</mark> beta <mark>ALPHA</mark>'
    );
  });

  it('returns escaped sentence unchanged when anchor is empty', () => {
    expect(highlightText('<b>Unsafe</b>', '')).toBe('&lt;b&gt;Unsafe&lt;/b&gt;');
  });

  it('escapes the anchor before constructing the highlight regex', () => {
    expect(highlightText('Use C++ and C#.', 'C++')).toBe(
      'Use <mark>C++</mark> and C#.'
    );
  });
});
