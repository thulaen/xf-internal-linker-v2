import {
  ChangeDetectionStrategy,
  Component,
  Input,
  OnDestroy,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Phase D2 / Gap 75 — Read-aloud TTS button.
 *
 * Drop next to any prose-y text (Status Story headline, Mission Brief
 * sentences) to give it a small play/stop button. Uses the browser's
 * native Web Speech API — no network call, no third-party voice.
 *
 * Usage:
 *
 *   <app-read-aloud
 *     [text]="missionBrief.sentences.join(' ')"
 *     label="Read mission brief aloud" />
 *
 * Hidden entirely when the browser doesn't expose `speechSynthesis`
 * (some embedded browsers, very old IE). On supporting browsers, the
 * button toggles between "play" and "stop"; the speech instance is
 * tied to this component, so navigating away cancels it cleanly.
 */
@Component({
  selector: 'app-read-aloud',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatTooltipModule],
  template: `
    @if (supported) {
      <button
        mat-icon-button
        type="button"
        class="ra-btn"
        [class.ra-btn-active]="speaking()"
        [matTooltip]="speaking() ? 'Stop reading' : label"
        [attr.aria-label]="speaking() ? 'Stop reading' : label"
        [attr.aria-pressed]="speaking()"
        (click)="toggle()"
      >
        <mat-icon>{{ speaking() ? 'stop' : 'volume_up' }}</mat-icon>
      </button>
    }
  `,
  styles: [`
    .ra-btn {
      transition: color 0.15s ease;
    }
    .ra-btn-active {
      color: var(--color-primary);
    }
    @media (prefers-reduced-motion: reduce) {
      .ra-btn { transition: none; }
    }
  `],
})
export class ReadAloudComponent implements OnDestroy {
  /** Text to speak. Re-reading the same component with new text replaces. */
  @Input({ required: true }) text = '';
  /** ARIA label and tooltip text shown when not currently speaking. */
  @Input() label = 'Read aloud';

  readonly supported =
    typeof window !== 'undefined' &&
    typeof window.speechSynthesis !== 'undefined' &&
    typeof window.SpeechSynthesisUtterance !== 'undefined';

  readonly speaking = signal(false);
  private utterance: SpeechSynthesisUtterance | null = null;

  toggle(): void {
    if (!this.supported) return;
    if (this.speaking()) {
      this.stop();
    } else {
      this.speak();
    }
  }

  private speak(): void {
    const text = (this.text ?? '').trim();
    if (!text) return;
    // Cancel anything else mid-flight so two read-aloud buttons don't
    // talk over each other.
    window.speechSynthesis.cancel();

    const u = new SpeechSynthesisUtterance(text);
    // Reasonable defaults — slightly slower than default for clarity.
    u.rate = 1.0;
    u.pitch = 1.0;
    u.lang = document.documentElement.lang || 'en-US';
    u.onend = () => this.speaking.set(false);
    u.onerror = () => this.speaking.set(false);
    this.utterance = u;
    this.speaking.set(true);
    window.speechSynthesis.speak(u);
  }

  private stop(): void {
    if (!this.supported) return;
    window.speechSynthesis.cancel();
    this.speaking.set(false);
    this.utterance = null;
  }

  ngOnDestroy(): void {
    if (this.speaking()) this.stop();
  }
}
