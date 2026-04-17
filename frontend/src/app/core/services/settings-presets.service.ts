import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

/**
 * Phase MX2 / Gap 307 — Settings presets.
 *
 * Three one-click bundles the Preference Center + Settings page apply
 * to every tunable knob:
 *
 *   * conservative — low-risk defaults. Weights from the published
 *                    `recommended` preset. Aggressive signals OFF.
 *   * balanced     — the production default most installs should use.
 *                    Matches the current shipped `RECOMMENDED` preset.
 *   * aggressive   — high-recall tuning for operators willing to
 *                    triage more false positives. Turns on experimental
 *                    signals + relaxes dedup.
 *
 * The mapping lives server-side so presets evolve with the product
 * without a frontend deploy. This service is just the HTTP client.
 */

export type PresetId = 'conservative' | 'balanced' | 'aggressive';

export interface SettingsPreset {
  id: PresetId;
  label: string;
  description: string;
  /** Absolute count of AppSetting keys the preset will change. */
  touches: number;
}

export interface ApplyPresetResult {
  applied: number;
  skipped: number;
  keys: string[];
}

@Injectable({ providedIn: 'root' })
export class SettingsPresetsService {
  private http = inject(HttpClient);
  private readonly base = '/api/settings/presets/';

  /** Static catalogue — fine to keep client-side; the preset payloads
   *  themselves live on the server. */
  readonly presets: readonly SettingsPreset[] = [
    {
      id: 'conservative',
      label: 'Conservative',
      description:
        'Low-risk defaults. Aggressive signals off; reviewer sees only the strongest suggestions.',
      touches: 0,
    },
    {
      id: 'balanced',
      label: 'Balanced (recommended)',
      description:
        'Production default. Matches the published research-backed weights.',
      touches: 0,
    },
    {
      id: 'aggressive',
      label: 'Aggressive',
      description:
        'High-recall tuning for operators willing to triage more rows. Experimental signals ON.',
      touches: 0,
    },
  ];

  /** Preview without applying — returns the key → new_value map. */
  preview(id: PresetId): Observable<Record<string, string>> {
    return this.http.get<Record<string, string>>(`${this.base}${id}/preview/`);
  }

  apply(id: PresetId): Observable<ApplyPresetResult> {
    return this.http.post<ApplyPresetResult>(`${this.base}${id}/apply/`, {});
  }
}
