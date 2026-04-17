import { ChangeDetectionStrategy, Component, Input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase D3 / Gap 184 — 30-second video-tutorial slot.
 *
 * Drop next to a card title to expose a tiny "How to use this" video
 * link:
 *
 *   <app-video-tutorial
 *     title="How the suggestion funnel works"
 *     videoUrl="https://docs.example.com/clips/funnel.mp4"
 *     posterUrl="..." />
 *
 * The component shows only a play-button chip until clicked; on
 * click it expands inline to an HTML5 `<video>` with controls. No
 * autoplay, no third-party SDK — sticking with native means it
 * works offline if the URL is on the same origin and a future MDN
 * change can't break us.
 *
 * If `videoUrl` is empty, the component renders nothing so empty
 * tutorial slots disappear cleanly.
 */
@Component({
  selector: 'app-video-tutorial',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  template: `
    @if (videoUrl) {
      @if (!playing()) {
        <button
          mat-stroked-button
          type="button"
          class="vt-trigger"
          (click)="play()"
        >
          <mat-icon>play_circle</mat-icon>
          <span class="vt-trigger-text">{{ title || 'Watch the 30-sec tutorial' }}</span>
        </button>
      } @else {
        <div class="vt-frame">
          <video
            [src]="videoUrl"
            [poster]="posterUrl || ''"
            controls
            preload="metadata"
            playsinline
            class="vt-video"
          ></video>
          <button
            mat-button
            type="button"
            class="vt-close"
            (click)="stop()"
          >
            <mat-icon>close</mat-icon>
            Close
          </button>
        </div>
      }
    }
  `,
  styles: [`
    .vt-trigger {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
    }
    .vt-trigger-text { font-weight: 500; }
    .vt-frame {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 8px;
      background: var(--color-bg-faint);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
    }
    .vt-video {
      width: 100%;
      max-width: 480px;
      border-radius: 4px;
      background: #000;
    }
    .vt-close { align-self: flex-end; }
  `],
})
export class VideoTutorialComponent {
  /** Tutorial label shown on the trigger button. */
  @Input() title = '';
  /** URL of the video file (mp4, webm, mov). Empty hides the slot. */
  @Input() videoUrl = '';
  /** Optional poster shown before the video starts. */
  @Input() posterUrl = '';

  readonly playing = signal(false);

  play(): void { this.playing.set(true); }
  stop(): void { this.playing.set(false); }
}
