/**
 * AudioCueService — plays short packaged chimes for alert events.
 *
 * Rules:
 *  - Sound must be user-configurable (on/off + minimum severity).
 *  - Sound must obey quiet hours.
 *  - Sound must never loop.
 *  - Sound fires at most once per deduped alert event (browser AudioContext
 *    approach avoids needing external audio files).
 */

import { Injectable } from '@angular/core';
import { OperatorAlert } from './notification.service';

const SEVERITY_RANK: Record<string, number> = {
  info: 0,
  success: 1,
  warning: 2,
  error: 3,
  urgent: 4,
};

@Injectable({ providedIn: 'root' })
export class AudioCueService {
  private ctx: AudioContext | null = null;

  /**
   * Play an audio cue for an alert if severity meets the threshold and
   * quiet hours are not active.
   */
  playForAlert(
    alert: OperatorAlert,
    minSeverity = 'error',
    quietHoursActive = false,
  ): void {
    if (quietHoursActive) return;

    const alertRank = SEVERITY_RANK[alert.severity] ?? 0;
    const minRank = SEVERITY_RANK[minSeverity] ?? 3;
    if (alertRank < minRank) return;

    if (alert.severity === 'urgent' || alert.severity === 'error') {
      this.playTone('error');
    } else if (alert.severity === 'warning') {
      this.playTone('warning');
    } else if (alert.severity === 'success') {
      this.playTone('success');
    }
  }

  /** Play a named tone type. */
  playTone(type: 'success' | 'warning' | 'error'): void {
    try {
      if (!this.ctx) {
        this.ctx = new AudioContext();
      }
      const ctx = this.ctx;

      const oscillator = ctx.createOscillator();
      const gainNode = ctx.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(ctx.destination);

      const now = ctx.currentTime;

      if (type === 'success') {
        // Two rising tones — pleasant completion sound
        oscillator.frequency.setValueAtTime(660, now);
        oscillator.frequency.setValueAtTime(880, now + 0.1);
        gainNode.gain.setValueAtTime(0.15, now);
        gainNode.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
        oscillator.start(now);
        oscillator.stop(now + 0.4);
      } else if (type === 'warning') {
        // Single mid tone
        oscillator.frequency.setValueAtTime(520, now);
        gainNode.gain.setValueAtTime(0.15, now);
        gainNode.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
        oscillator.start(now);
        oscillator.stop(now + 0.35);
      } else {
        // Two descending tones — urgent/error
        oscillator.frequency.setValueAtTime(440, now);
        oscillator.frequency.setValueAtTime(330, now + 0.15);
        gainNode.gain.setValueAtTime(0.2, now);
        gainNode.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
        oscillator.start(now);
        oscillator.stop(now + 0.5);
      }
    } catch {
      // AudioContext unavailable or blocked — fail silently
    }
  }
}
