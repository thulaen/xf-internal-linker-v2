import { ChangeDetectionStrategy, Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase D3 / Gap 172 — Layman's flow diagram card.
 *
 * A simple horizontal "how this app works" diagram in plain English.
 * Five stages: Source → Crawl/Import → Parse → Score → Suggest. Each
 * step is a labelled icon connected by an arrow.
 *
 * Pure SVG — no chart library, no third-party diagram engine. Static
 * because the pipeline shape doesn't change between sessions.
 */
@Component({
  selector: 'app-flow-diagram',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatCardModule, MatIconModule],
  template: `
    <mat-card class="fd-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="fd-avatar">schema</mat-icon>
        <mat-card-title>How this app works</mat-card-title>
        <mat-card-subtitle>Five steps from source to suggestion</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <ol class="fd-flow">
          <li class="fd-step">
            <mat-icon class="fd-step-icon">cloud_download</mat-icon>
            <span class="fd-step-label">Source</span>
            <span class="fd-step-detail">XenForo · WordPress · JSONL upload</span>
          </li>
          <li class="fd-arrow"><mat-icon>arrow_forward</mat-icon></li>
          <li class="fd-step">
            <mat-icon class="fd-step-icon">travel_explore</mat-icon>
            <span class="fd-step-label">Crawl &amp; import</span>
            <span class="fd-step-detail">Fetch + dedupe pages</span>
          </li>
          <li class="fd-arrow"><mat-icon>arrow_forward</mat-icon></li>
          <li class="fd-step">
            <mat-icon class="fd-step-icon">psychology</mat-icon>
            <span class="fd-step-label">Parse &amp; embed</span>
            <span class="fd-step-detail">spaCy + vector embeddings</span>
          </li>
          <li class="fd-arrow"><mat-icon>arrow_forward</mat-icon></li>
          <li class="fd-step">
            <mat-icon class="fd-step-icon">tune</mat-icon>
            <span class="fd-step-label">Score &amp; rank</span>
            <span class="fd-step-detail">23 signals, weighted ensemble</span>
          </li>
          <li class="fd-arrow"><mat-icon>arrow_forward</mat-icon></li>
          <li class="fd-step">
            <mat-icon class="fd-step-icon">recommend</mat-icon>
            <span class="fd-step-label">Suggest</span>
            <span class="fd-step-detail">Reviewable link suggestions</span>
          </li>
        </ol>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .fd-card { width: 100%; }
    .fd-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .fd-flow {
      list-style: none;
      margin: 0;
      padding: 8px 0;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
    }
    .fd-step {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
      padding: 12px;
      background: var(--color-bg-faint);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      flex: 1 1 140px;
      min-width: 120px;
      text-align: center;
    }
    .fd-step-icon {
      font-size: 28px;
      width: 28px;
      height: 28px;
      color: var(--color-primary);
      margin-bottom: 4px;
    }
    .fd-step-label {
      font-weight: 500;
      font-size: 13px;
      color: var(--color-text-primary);
    }
    .fd-step-detail {
      font-size: 11px;
      color: var(--color-text-secondary);
      line-height: 1.4;
    }
    .fd-arrow {
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--color-text-secondary);
    }
    .fd-arrow mat-icon {
      font-size: 22px;
      width: 22px;
      height: 22px;
    }
    @media (max-width: 720px) {
      .fd-flow { flex-direction: column; }
      .fd-arrow {
        transform: rotate(90deg);
      }
    }
  `],
})
export class FlowDiagramComponent {}
