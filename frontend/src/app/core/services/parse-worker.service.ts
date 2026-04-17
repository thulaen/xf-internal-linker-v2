import { Injectable } from '@angular/core';

/**
 * Phase F1 / Gap 85 — Web Worker offloader for JSON / CSV parses.
 *
 * Lazily spawns one shared Worker on first parse request. All
 * subsequent calls reuse it. Each request gets a unique id so
 * concurrent callers can interleave their requests without confusion.
 *
 * Falls back to a synchronous main-thread parse if Worker construction
 * fails (e.g. CSP blocks workers, ancient browser). The fallback path
 * is documented but not optimised — the whole point of this service
 * is to avoid main-thread parses, so the fallback should be rare.
 *
 * Usage:
 *
 *   constructor(private parser: ParseWorkerService) {}
 *
 *   async loadCsv(text: string): Promise<unknown> {
 *     return await this.parser.parseCsv(text);
 *   }
 */
@Injectable({ providedIn: 'root' })
export class ParseWorkerService {
  private worker: Worker | null = null;
  private nextId = 1;
  private pending = new Map<
    string,
    { resolve: (v: unknown) => void; reject: (e: Error) => void }
  >();

  /** Parse a JSON string off the main thread. Returns the decoded
   *  value or rejects with the parser's error. */
  parseJson(text: string): Promise<unknown> {
    return this.send({ kind: 'json', text });
  }

  /** Parse a CSV string off the main thread.
   *  When `hasHeader` (default true) the result is an array of objects
   *  keyed by the header row; otherwise it's a 2D array of strings. */
  parseCsv(text: string, hasHeader = true): Promise<unknown> {
    return this.send({ kind: 'csv', text, hasHeader });
  }

  // ── internals ──────────────────────────────────────────────────────

  private send(req: { kind: 'json' | 'csv'; text: string; hasHeader?: boolean }): Promise<unknown> {
    const w = this.ensureWorker();
    if (!w) {
      // Fallback — main-thread parse. Only triggers when Worker
      // construction failed (CSP, ancient browser, etc.).
      return this.fallback(req);
    }
    const id = String(this.nextId++);
    return new Promise<unknown>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      w.postMessage({ id, ...req });
    });
  }

  private ensureWorker(): Worker | null {
    if (this.worker) return this.worker;
    if (typeof Worker === 'undefined') return null;
    try {
      this.worker = new Worker(
        new URL('../workers/parse.worker.ts', import.meta.url),
        { type: 'module' },
      );
    } catch {
      this.worker = null;
      return null;
    }
    this.worker.addEventListener('message', (event) => {
      const msg = event.data as
        | { id: string; ok: true; result: unknown }
        | { id: string; ok: false; error: string };
      const slot = this.pending.get(msg.id);
      if (!slot) return;
      this.pending.delete(msg.id);
      if (msg.ok) slot.resolve(msg.result);
      else slot.reject(new Error(msg.error));
    });
    return this.worker;
  }

  private async fallback(req: { kind: 'json' | 'csv'; text: string; hasHeader?: boolean }): Promise<unknown> {
    if (req.kind === 'json') return JSON.parse(req.text);
    // Minimal main-thread CSV fallback — duplicates the worker logic
    // but only runs in the rare no-Worker case.
    const rows: string[][] = [];
    let row: string[] = [];
    let cell = '';
    let inQuotes = false;
    for (let i = 0; i < req.text.length; i++) {
      const c = req.text[i];
      if (inQuotes) {
        if (c === '"' && req.text[i + 1] === '"') { cell += '"'; i++; continue; }
        if (c === '"') { inQuotes = false; continue; }
        cell += c; continue;
      }
      if (c === '"' && cell === '') { inQuotes = true; continue; }
      if (c === ',') { row.push(cell); cell = ''; continue; }
      if (c === '\r' || c === '\n') {
        if (c === '\r' && req.text[i + 1] === '\n') i++;
        row.push(cell); rows.push(row); row = []; cell = '';
        continue;
      }
      cell += c;
    }
    if (cell.length > 0 || row.length > 0) { row.push(cell); rows.push(row); }
    if (!(req.hasHeader ?? true)) return rows;
    if (rows.length === 0) return [];
    const header = rows[0];
    return rows.slice(1).map((r) => {
      const o: Record<string, string> = {};
      for (let j = 0; j < header.length; j++) o[header[j]] = r[j] ?? '';
      return o;
    });
  }
}
