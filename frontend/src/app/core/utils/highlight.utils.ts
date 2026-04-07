/** Escape special HTML characters to prevent XSS / unintended rendering. */
export function escapeHtml(text: string): string {
  return (text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

const _HIGHLIGHT_CACHE_MAX = 500;
const highlightCache = new Map<string, string>();

export function highlightText(sentence: string, anchor: string): string {
  const key = `${sentence}|||${anchor}`;
  if (highlightCache.has(key)) {
    return highlightCache.get(key)!;
  }

  const safeSentence = escapeHtml(sentence);
  if (!anchor) {
    return safeSentence;
  }
  const safeAnchor = escapeHtml(anchor);
  const reEsc = safeAnchor.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const result = safeSentence.replace(new RegExp(`(${reEsc})`, 'gi'), '<mark>$1</mark>');

  // Evict the oldest entry (Map preserves insertion order) rather than
  // clearing everything at once, which would cause a burst of cache misses.
  if (highlightCache.size >= _HIGHLIGHT_CACHE_MAX) {
    highlightCache.delete(highlightCache.keys().next().value!);
  }
  highlightCache.set(key, result);
  return result;
}
