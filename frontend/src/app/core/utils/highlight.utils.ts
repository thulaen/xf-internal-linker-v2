/** Escape special HTML characters to prevent XSS / unintended rendering. */
export function escapeHtml(text: string): string {
  return (text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Wrap occurrences of `anchor` inside `sentence` with `<mark>` tags.
 * Both inputs are HTML-escaped first so raw forum content cannot inject markup.
 * Returns a safe HTML string ready for use with bypassSecurityTrustHtml or [innerHTML].
 */
export function highlightText(sentence: string, anchor: string): string {
  const safeSentence = escapeHtml(sentence);
  if (!anchor) return safeSentence;
  const safeAnchor = escapeHtml(anchor);
  const reEsc = safeAnchor.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return safeSentence.replace(new RegExp(`(${reEsc})`, 'gi'), '<mark>$1</mark>');
}
