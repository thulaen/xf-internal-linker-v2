/**
 * Phase DC / Gap 124 — Minimal safe Markdown renderer.
 *
 * Supports the subset that covers 99% of operator-facing text:
 *   - `# H1` / `## H2` / `### H3`
 *   - `**bold**`, `*italic*`, `` `code` ``
 *   - `[label](url)` (same-origin relative + https absolute)
 *   - `- bullet lists`, `1. ordered lists`
 *   - blockquotes (`> `)
 *   - triple-backtick code blocks
 *   - paragraphs (blank line)
 *
 * Everything else is passed through as literal text — NO raw HTML
 * rendering, NO image embedding, NO script tags. The renderer is
 * the sanitisation boundary; we can't render what we don't parse.
 *
 * Why roll our own: pulling in `marked` + `dompurify` is ~60kB for
 * features we don't use. The stripped-down subset above is ~150 lines
 * and fits a single file.
 */

const ESCAPE_MAP: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ESCAPE_MAP[c] ?? c);
}

function safeUrl(raw: string): string {
  const trimmed = raw.trim();
  if (/^(?:https?:\/\/|\/|#|mailto:)/i.test(trimmed)) {
    return escapeHtml(trimmed);
  }
  return '#';
}

/**
 * Convert a line of inline markdown to HTML. Order matters:
 *   1. Escape raw HTML first.
 *   2. Replace fenced code (`` `x` ``) before bold/italic so underscores
 *      inside code don't trigger emphasis.
 *   3. Replace links before bold so the `[x](y)` bracket isn't chewed.
 *   4. Replace **bold**, then *italic*.
 */
function renderInline(line: string): string {
  let s = escapeHtml(line);
  s = s.replace(/`([^`]+)`/g, (_, code) => `<code>${code}</code>`);
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label: string, url: string) => {
    return `<a href="${safeUrl(url)}" rel="noopener noreferrer" target="_blank">${escapeHtml(
      label,
    )}</a>`;
  });
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  return s;
}

/** Render a block of markdown text to HTML. */
export function renderMarkdown(text: string): string {
  if (!text) return '';
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const out: string[] = [];
  let i = 0;

  const closeLists = (stack: string[]) => {
    while (stack.length > 0) out.push(`</${stack.pop()}>`);
  };

  const listStack: string[] = [];

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code blocks (``` … ```)
    if (/^```/.test(line)) {
      closeLists(listStack);
      const buf: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        buf.push(escapeHtml(lines[i]));
        i++;
      }
      out.push(`<pre><code>${buf.join('\n')}</code></pre>`);
      if (i < lines.length) i++; // skip the closing fence
      continue;
    }

    // Blockquote
    if (/^\s*>\s?/.test(line)) {
      closeLists(listStack);
      const buf: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        buf.push(renderInline(lines[i].replace(/^\s*>\s?/, '')));
        i++;
      }
      out.push(`<blockquote>${buf.join('<br />')}</blockquote>`);
      continue;
    }

    // Heading
    const h = /^(#{1,3})\s+(.+)$/.exec(line);
    if (h) {
      closeLists(listStack);
      const level = h[1].length;
      out.push(`<h${level + 2}>${renderInline(h[2])}</h${level + 2}>`);
      i++;
      continue;
    }

    // Unordered list
    if (/^\s*[-*]\s+/.test(line)) {
      if (listStack[listStack.length - 1] !== 'ul') {
        closeLists(listStack);
        out.push('<ul>');
        listStack.push('ul');
      }
      out.push(`<li>${renderInline(line.replace(/^\s*[-*]\s+/, ''))}</li>`);
      i++;
      continue;
    }

    // Ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      if (listStack[listStack.length - 1] !== 'ol') {
        closeLists(listStack);
        out.push('<ol>');
        listStack.push('ol');
      }
      out.push(`<li>${renderInline(line.replace(/^\s*\d+\.\s+/, ''))}</li>`);
      i++;
      continue;
    }

    // Blank line → paragraph break / close lists
    if (line.trim() === '') {
      closeLists(listStack);
      i++;
      continue;
    }

    // Paragraph
    closeLists(listStack);
    const buf: string[] = [renderInline(line)];
    i++;
    while (i < lines.length && lines[i].trim() !== '' && !/^```|^#{1,3}\s|^\s*[-*]\s|^\s*\d+\.\s|^\s*>\s/.test(lines[i])) {
      buf.push(renderInline(lines[i]));
      i++;
    }
    out.push(`<p>${buf.join('<br />')}</p>`);
  }
  closeLists(listStack);
  return out.join('\n');
}
