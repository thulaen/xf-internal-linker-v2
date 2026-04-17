import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  inject,
  signal,
} from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';

import { NetworkWaterfallService } from '../../../core/services/network-waterfall.service';
import { PerfMonitorService } from '../../../core/services/perf-monitor.service';

/**
 * Phase OB / Gaps 133 + 134 + 135 + 136 — Developer Debug Overlay.
 *
 * Press **Shift+D** to toggle a floating panel that combines four
 * diagnostic views:
 *
 *   - Long tasks (> 50ms) from `PerfMonitorService` (Gap 134)
 *   - Memory pressure samples over time (Gap 135)
 *   - Network waterfall for every fetch / XHR / asset (Gap 136)
 *   - Route + render stats — current route, last click, time origin
 *
 * Only renders when the keyboard shortcut has been pressed. Visually
 * does NOT use our Material tokens so it's unmistakable against any
 * page palette — debug overlay looks like a debug overlay, even in
 * high-contrast mode.
 *
 * Lives in the global shell (mounted from AppComponent template).
 * Starts the monitor services on first open so production users who
 * never open the overlay never pay their cost.
 */
@Component({
  selector: 'app-debug-overlay',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DecimalPipe,
    MatButtonModule,
    MatIconModule,
    MatTabsModule,
  ],
  template: `
    @if (open()) {
      <aside class="do" role="dialog" aria-label="Debug overlay">
        <header class="do-head">
          <span>🔧 Debug overlay</span>
          <button
            type="button"
            class="do-close"
            aria-label="Close"
            (click)="toggle()"
          >×</button>
        </header>
        <mat-tab-group>
          <mat-tab label="Long tasks ({{ perf.longTasks().length }})">
            @if (perf.longTasks().length === 0) {
              <p class="do-empty">No long tasks observed yet.</p>
            } @else {
              <table class="do-table">
                <thead>
                  <tr>
                    <th>At</th>
                    <th>Duration</th>
                    <th>Attribution</th>
                  </tr>
                </thead>
                <tbody>
                  @for (lt of perf.longTasks(); track lt.at) {
                    <tr>
                      <td>{{ formatClock(lt.at) }}</td>
                      <td class="do-num">{{ lt.duration | number:'1.0-1' }}ms</td>
                      <td>{{ lt.attribution }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </mat-tab>

          <mat-tab label="Memory ({{ perf.memorySamples().length }})">
            @if (perf.memorySamples().length === 0) {
              <p class="do-empty">
                No memory samples. (Chromium-only; dev mode only.)
              </p>
            } @else {
              <table class="do-table">
                <thead>
                  <tr>
                    <th>At</th>
                    <th>Used</th>
                    <th>Limit</th>
                    <th>Pressure</th>
                  </tr>
                </thead>
                <tbody>
                  @for (m of perf.memorySamples(); track m.at) {
                    <tr [class.do-row-alarm]="m.pressure > 0.85">
                      <td>{{ formatClock(m.at) }}</td>
                      <td class="do-num">{{ m.usedHeapMb | number:'1.0-1' }} MB</td>
                      <td class="do-num">{{ m.heapLimitMb | number:'1.0-1' }} MB</td>
                      <td class="do-num">{{ (m.pressure * 100) | number:'1.0-0' }}%</td>
                    </tr>
                  }
                </tbody>
              </table>
              @if (perf.memoryAlarm()) {
                <p class="do-alarm">
                  ⚠ Heap pressure exceeded 85% of the limit — likely a leak.
                </p>
              }
            }
          </mat-tab>

          <mat-tab label="Network ({{ network.entries().length }})">
            @if (network.entries().length === 0) {
              <p class="do-empty">No network entries captured.</p>
            } @else {
              <table class="do-table">
                <thead>
                  <tr>
                    <th>Start</th>
                    <th>Duration</th>
                    <th>Size</th>
                    <th>Type</th>
                    <th>URL</th>
                  </tr>
                </thead>
                <tbody>
                  @for (e of network.entries(); track e.id) {
                    <tr [class.do-row-cached]="e.status === 'cached'">
                      <td class="do-num">{{ e.startedAt | number:'1.0-0' }}ms</td>
                      <td class="do-num">{{ e.duration | number:'1.0-1' }}ms</td>
                      <td class="do-num">{{ e.transferSizeKb | number:'1.0-1' }} KB</td>
                      <td>{{ e.initiatorType }}</td>
                      <td class="do-url">{{ e.url }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </mat-tab>
        </mat-tab-group>

        <footer class="do-footer">
          <button mat-button type="button" (click)="clearAll()">
            Clear
          </button>
          <span class="do-keyhint">Shift + D to close</span>
        </footer>
      </aside>
    }
  `,
  styles: [`
    .do {
      position: fixed;
      bottom: 0;
      right: 0;
      width: min(560px, 96vw);
      max-height: 70vh;
      background: #1e1e1e;
      color: #e8eaed;
      border-top-left-radius: 8px;
      box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.35);
      font-family: var(--font-mono, ui-monospace, SFMono-Regular, monospace);
      font-size: 11px;
      z-index: 9995;
      display: flex;
      flex-direction: column;
    }
    .do-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 10px;
      background: #111;
      color: #fff;
      font-size: 12px;
      font-weight: 500;
    }
    .do-close {
      background: transparent;
      border: 0;
      color: inherit;
      font-size: 18px;
      line-height: 1;
      cursor: pointer;
    }
    mat-tab-group {
      flex: 1;
      overflow: hidden;
    }
    .do-empty {
      padding: 16px;
      color: #9aa0a6;
      font-style: italic;
    }
    .do-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
    }
    .do-table th, .do-table td {
      padding: 4px 8px;
      border-bottom: 1px solid #3c4043;
      vertical-align: top;
    }
    .do-table thead th {
      position: sticky;
      top: 0;
      background: #2d2f31;
      color: #bdc1c6;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      font-size: 10px;
    }
    .do-num { text-align: right; font-variant-numeric: tabular-nums; }
    .do-url { word-break: break-all; }
    .do-row-alarm { background: rgba(217, 48, 37, 0.2); }
    .do-row-cached { opacity: 0.7; }
    .do-alarm {
      margin: 8px 12px 0;
      padding: 6px 10px;
      background: rgba(217, 48, 37, 0.2);
      border-left: 3px solid #d93025;
    }
    .do-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 10px;
      background: #2d2f31;
      border-top: 1px solid #3c4043;
    }
    .do-keyhint {
      color: #9aa0a6;
      font-size: 10px;
    }
  `],
})
export class DebugOverlayComponent {
  readonly perf = inject(PerfMonitorService);
  readonly network = inject(NetworkWaterfallService);

  readonly open = signal(false);

  @HostListener('document:keydown', ['$event'])
  onKeydown(event: KeyboardEvent): void {
    // Shift+D, but NOT Ctrl+Shift+D (browser devtools shortcut on some
    // platforms), NOT while typing in an input.
    if (!event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
    if ((event.key ?? '').toLowerCase() !== 'd') return;
    const target = event.target as HTMLElement | null;
    if (target) {
      const tag = target.tagName.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable) {
        return;
      }
    }
    event.preventDefault();
    this.toggle();
  }

  toggle(): void {
    const next = !this.open();
    this.open.set(next);
    if (next) {
      this.perf.start();
      this.network.start();
    }
  }

  clearAll(): void {
    this.perf.clear();
    this.network.clear();
  }

  formatClock(ms: number): string {
    const d = new Date(ms);
    const hh = d.getHours().toString().padStart(2, '0');
    const mm = d.getMinutes().toString().padStart(2, '0');
    const ss = d.getSeconds().toString().padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
  }
}
