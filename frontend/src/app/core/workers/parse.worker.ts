/// <reference lib="webworker" />

/**
 * Phase F1 / Gap 85 — JSON / CSV parsing Web Worker.
 *
 * Heavy parses (a 5MB suggestion-export CSV, or a denormalised
 * suggestion explainer JSON) block the main thread for hundreds of
 * milliseconds in Chrome and trigger jank scores via Web Vitals (INP,
 * TBT). Offloading parse + light transform to a Worker keeps the main
 * thread responsive.
 *
 * Message protocol (from main thread):
 *   { id: string, kind: 'json', text: string }
 *   { id: string, kind: 'csv',  text: string, hasHeader?: boolean }
 *
 * Reply (from worker):
 *   { id: string, ok: true,  result: unknown }
 *   { id: string, ok: false, error: string }
 *
 * Use via `ParseWorkerService` (in services/) — never instantiate the
 * Worker directly from a component.
 */

interface ParseRequest {
  id: string;
  kind: 'json' | 'csv';
  text: string;
  hasHeader?: boolean;
}

interface ParseSuccess {
  id: string;
  ok: true;
  result: unknown;
}

interface ParseFailure {
  id: string;
  ok: false;
  error: string;
}

addEventListener('message', (event: MessageEvent<ParseRequest>) => {
  const req = event.data;
  if (!req || typeof req !== 'object' || !req.id || !req.kind) {
    return;
  }
  try {
    let result: unknown;
    if (req.kind === 'json') {
      result = JSON.parse(req.text);
    } else if (req.kind === 'csv') {
      result = parseCsv(req.text, req.hasHeader ?? true);
    } else {
      throw new Error(`unsupported kind: ${(req as { kind: string }).kind}`);
    }
    const reply: ParseSuccess = { id: req.id, ok: true, result };
    postMessage(reply);
  } catch (e) {
    const reply: ParseFailure = {
      id: req.id,
      ok: false,
      error: e instanceof Error ? e.message : String(e),
    };
    postMessage(reply);
  }
});

/**
 * RFC-4180-aware CSV parser. Handles:
 *   - Quoted fields with embedded commas, CR, LF.
 *   - Escaped quotes via doubling ("she said ""hi""").
 *   - Trailing newline tolerance.
 *
 * Returns either an array of objects (when hasHeader) or an array of
 * arrays. Streaming would be nicer for very large inputs but the
 * dashboard caps client-side CSV at ~10MB which fits comfortably in
 * RAM as one string.
 */
function parseCsv(text: string, hasHeader: boolean): unknown {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let inQuotes = false;
  let i = 0;
  const N = text.length;

  while (i < N) {
    const c = text[i];

    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      cell += c;
      i++;
      continue;
    }

    // Not in quotes
    if (c === '"' && cell === '') {
      inQuotes = true;
      i++;
      continue;
    }
    if (c === ',') {
      row.push(cell);
      cell = '';
      i++;
      continue;
    }
    if (c === '\r') {
      if (text[i + 1] === '\n') i++;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
      i++;
      continue;
    }
    if (c === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
      i++;
      continue;
    }
    cell += c;
    i++;
  }
  // Trailing cell / row
  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  if (!hasHeader) return rows;
  if (rows.length === 0) return [];
  const header = rows[0];
  return rows.slice(1).map((r) => {
    const obj: Record<string, string> = {};
    for (let j = 0; j < header.length; j++) {
      obj[header[j]] = r[j] ?? '';
    }
    return obj;
  });
}
