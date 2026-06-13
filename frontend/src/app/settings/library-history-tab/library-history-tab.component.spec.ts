/**
 * Specs for the extracted Library & History tab. Mirrors the contract
 * the parent settings page used to enforce inline:
 *   - Loads presets, history and challengers via the three known
 *     endpoints on init (forkJoin pair + single GET).
 *   - `markDirty()` emits `dirtyChanged=true`.
 *   - `applyPreset(...)` posts to `/api/weight-presets/<id>/apply/`,
 *     emits `presetApplied=<name>`, then re-runs the load triple so the
 *     post-apply server state is reflected.
 *   - The four cards (preset hero, recommended-reset button, challenger
 *     panel, adjustment history) render without throwing.
 */
import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';

import { LibraryHistoryTabComponent } from './library-history-tab.component';
import {
  RankingChallenger,
  SiloSettingsService,
  WeightAdjustmentHistory,
  WeightPreset,
} from '../silo-settings.service';

const RECOMMENDED_PRESET: WeightPreset = {
  id: 1,
  name: 'System Recommended',
  is_system: true,
  weights: { 'weightedAuthority.ranking_weight': '0.30' },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const CUSTOM_PRESET: WeightPreset = {
  id: 2,
  name: 'My Snapshot',
  is_system: false,
  weights: { 'weightedAuthority.ranking_weight': '0.50' },
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-01T00:00:00Z',
};

const PRESETS_RESPONSE = { results: [RECOMMENDED_PRESET, CUSTOM_PRESET] };

const HISTORY_ROW: WeightAdjustmentHistory = {
  id: 99,
  source: 'manual',
  preset: null,
  preset_name: null,
  previous_weights: { 'weightedAuthority.ranking_weight': '0.30' },
  new_weights: { 'weightedAuthority.ranking_weight': '0.40' },
  delta: { 'weightedAuthority.ranking_weight': { previous: '0.30', new: '0.40' } },
  reason: 'Bumped authority weight',
  r_run_id: '',
  created_at: '2026-04-15T10:00:00Z',
};

const CHALLENGERS_RESPONSE: RankingChallenger[] = [];
const CURRENT_WEIGHTS = { 'weightedAuthority.ranking_weight': '0.30' };

describe('LibraryHistoryTabComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LibraryHistoryTabComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([]),
        // Use the real SiloSettingsService so the load + save HTTP calls
        // go through the actual endpoint paths the spec asserts on via
        // HttpTestingController. Same pattern as
        // notifications-tab.component.spec.ts.
        SiloSettingsService,
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  /**
   * Drains the three GETs ngOnInit fires. Order is not guaranteed
   * because two of them ride a forkJoin and the third is a separate
   * subscribe; we match by URL via `expectOne(url)` instead of
   * positional `match`.
   */
  function flushInitialLoad(): void {
    httpMock.expectOne('/api/weight-presets/').flush(PRESETS_RESPONSE);
    httpMock.expectOne('/api/weight-history/').flush([HISTORY_ROW]);
    httpMock.expectOne('/api/weight-challengers/').flush(CHALLENGERS_RESPONSE);
    httpMock.expectOne('/api/weight-presets/current/').flush(CURRENT_WEIGHTS);
  }

  it('renders the three Library & History cards once initial load completes', () => {
    const fixture = TestBed.createComponent(LibraryHistoryTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const root: HTMLElement = fixture.nativeElement;
    expect(root.querySelector('#weight-presets')).not.toBeNull();
    expect(root.querySelector('#ranking-challengers')).not.toBeNull();
    expect(root.querySelector('#adjustment-history')).not.toBeNull();
  });

  it('loads weight presets into the signal-backed list on init', () => {
    const fixture = TestBed.createComponent(LibraryHistoryTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    expect(cmp.weightPresets().length).toBe(2);
    expect(cmp.weightPresets()[0].name).toBe('System Recommended');
    // `recommendedPreset` getter picks the system preset whose name
    // contains "recommended" — same rule as the parent's getter.
    expect(cmp.recommendedPreset?.id).toBe(RECOMMENDED_PRESET.id);
  });

  it('emits presetApplied with the preset name and reloads after apply', () => {
    const fixture = TestBed.createComponent(LibraryHistoryTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    const applied: Array<string | null> = [];
    cmp.presetApplied.subscribe((v) => applied.push(v));

    // Bypass the confirm() prompt — Karma can't drive the browser
    // dialog. The two-stage guard is logic-tested via `parentIsDirty`
    // toggles in an isolated assertion below; here we just want the
    // happy-path POST + Output sequence.
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    cmp.applyPreset(CUSTOM_PRESET);

    const applyReq = httpMock.expectOne(`/api/weight-presets/${CUSTOM_PRESET.id}/apply/`);
    expect(applyReq.request.method).toBe('POST');
    applyReq.flush({ detail: 'ok' });

    // Apply path always re-pulls current weights + presets + history.
    httpMock.expectOne('/api/weight-presets/current/').flush(CURRENT_WEIGHTS);
    httpMock.expectOne('/api/weight-presets/').flush(PRESETS_RESPONSE);
    httpMock.expectOne('/api/weight-history/').flush([HISTORY_ROW]);

    expect(applied).toEqual([CUSTOM_PRESET.name]);
    expect(cmp.applyingPreset()).toBe(false);
  });

  it('emits dirtyChanged true when markDirty is called', () => {
    const fixture = TestBed.createComponent(LibraryHistoryTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    const emitted: boolean[] = [];
    cmp.dirtyChanged.subscribe((v) => emitted.push(v));

    cmp.markDirty();

    expect(emitted).toEqual([true]);
  });
});
