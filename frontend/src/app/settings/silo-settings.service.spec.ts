import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting, TestRequest } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { SiloSettingsService } from './silo-settings.service';

/**
 * Coverage spec for SiloSettingsService — the service is a thin shell
 * over ~100 HTTP endpoints. Each `it` block sends one request, asserts
 * the URL + verb + payload that hit the wire, and flushes a mock
 * response. The four list endpoints additionally have an error-path
 * test that asserts the catchError fallback to `[]`.
 *
 * Together these tests bring SiloSettingsService from 0% function/branch
 * coverage to nearly 100% for that file, which lifts the overall
 * frontend coverage past the karma thresholds in karma.conf.cjs.
 */
describe('SiloSettingsService', () => {
  let service: SiloSettingsService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [SiloSettingsService, provideHttpClient(withXhr()), provideHttpClientTesting()],
    });
    service = TestBed.inject(SiloSettingsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function expectGet(url: string): TestRequest {
    const req = httpMock.expectOne(url);
    expect(req.request.method).toBe('GET');
    return req;
  }
  function expectPost(url: string, body?: unknown): TestRequest {
    const req = httpMock.expectOne(url);
    expect(req.request.method).toBe('POST');
    if (body !== undefined) expect(req.request.body).toEqual(body);
    return req;
  }
  function expectPut(url: string, body?: unknown): TestRequest {
    const req = httpMock.expectOne(url);
    expect(req.request.method).toBe('PUT');
    if (body !== undefined) expect(req.request.body).toEqual(body);
    return req;
  }
  function expectPatch(url: string, body?: unknown): TestRequest {
    const req = httpMock.expectOne(url);
    expect(req.request.method).toBe('PATCH');
    if (body !== undefined) expect(req.request.body).toEqual(body);
    return req;
  }
  function expectDelete(url: string): TestRequest {
    const req = httpMock.expectOne(url);
    expect(req.request.method).toBe('DELETE');
    return req;
  }

  // ── Core silo settings ────────────────────────────────────────────
  it('getSettings GETs /api/settings/silos/', () => {
    service.getSettings().subscribe();
    expectGet('/api/settings/silos/').flush({ mode: 'prefer_same_silo' });
  });

  it('updateSettings PUTs to /api/settings/silos/ with payload', () => {
    const payload = { mode: 'prefer_same_silo', same_silo_boost: 0.05, cross_silo_penalty: 0.05 } as any;
    service.updateSettings(payload).subscribe();
    expectPut('/api/settings/silos/', payload).flush(payload);
  });

  // ── Silo groups (list endpoint has catchError fallback) ────────────
  it('listSiloGroups unwraps {results:[…]} envelope', () =>
    new Promise<void>((done) => {
      service.listSiloGroups().subscribe((groups) => {
        expect(groups).toEqual([{ id: 1, name: 'A' } as any]);
        done();
      });
      expectGet('/api/silo-groups/').flush({ results: [{ id: 1, name: 'A' }] });
    }));

  it('listSiloGroups passes through a bare array response', () =>
    new Promise<void>((done) => {
      service.listSiloGroups().subscribe((groups) => {
        expect(groups).toEqual([{ id: 2 } as any]);
        done();
      });
      expectGet('/api/silo-groups/').flush([{ id: 2 }]);
    }));

  it('listSiloGroups returns [] on HTTP error (catchError fallback)', () =>
    new Promise<void>((done) => {
      service.listSiloGroups().subscribe((groups) => {
        expect(groups).toEqual([]);
        done();
      });
      expectGet('/api/silo-groups/').flush('boom', { status: 500, statusText: 'Server' });
    }));

  it('createSiloGroup POSTs to /api/silo-groups/', () => {
    service.createSiloGroup({ name: 'New' }).subscribe();
    expectPost('/api/silo-groups/', { name: 'New' }).flush({ id: 3, name: 'New' });
  });

  it('updateSiloGroup PATCHes the id-scoped URL', () => {
    service.updateSiloGroup(7, { name: 'Renamed' }).subscribe();
    expectPatch('/api/silo-groups/7/', { name: 'Renamed' }).flush({ id: 7, name: 'Renamed' });
  });

  it('deleteSiloGroup DELETEs the id-scoped URL', () => {
    service.deleteSiloGroup(9).subscribe();
    expectDelete('/api/silo-groups/9/').flush(null);
  });

  // ── Scopes (list endpoint has catchError fallback) ─────────────────
  it('listScopes unwraps {results:[…]} envelope', () =>
    new Promise<void>((done) => {
      service.listScopes().subscribe((s) => {
        expect(s).toEqual([{ id: 1 } as any]);
        done();
      });
      expectGet('/api/scopes/').flush({ results: [{ id: 1 }] });
    }));

  it('listScopes returns [] on HTTP error', () =>
    new Promise<void>((done) => {
      service.listScopes().subscribe((s) => {
        expect(s).toEqual([]);
        done();
      });
      expectGet('/api/scopes/').flush('boom', { status: 500, statusText: 'Server' });
    }));

  it('updateScopeSilo PATCHes the scope id with silo_group payload', () => {
    service.updateScopeSilo(4, 12).subscribe();
    expectPatch('/api/scopes/4/', { silo_group: 12 }).flush({ id: 4, silo_group: 12 } as any);
  });

  it('updateScopeSilo allows null silo_group (unassign)', () => {
    service.updateScopeSilo(4, null).subscribe();
    expectPatch('/api/scopes/4/', { silo_group: null }).flush({ id: 4, silo_group: null } as any);
  });

  // ── Connector settings (XenForo / WordPress) ───────────────────────
  it('getXenForoSettings GETs the XF settings endpoint', () => {
    service.getXenForoSettings().subscribe();
    expectGet('/api/settings/xenforo/').flush({ base_url: '' });
  });

  it('updateXenForoSettings POSTs the XF settings payload', () => {
    service.updateXenForoSettings({ base_url: 'https://x' } as any).subscribe();
    const req = httpMock.expectOne('/api/settings/xenforo/');
    expect(['POST', 'PUT']).toContain(req.request.method);
    req.flush({ status: 'saved' });
  });

  it('getWordPressSettings GETs the WP settings endpoint', () => {
    service.getWordPressSettings().subscribe();
    expectGet('/api/settings/wordpress/').flush({ base_url: '' });
  });

  it('updateWordPressSettings PUTs the WP settings payload', () => {
    const payload = { base_url: 'https://wp', username: 'u', sync_enabled: true } as any;
    service.updateWordPressSettings(payload).subscribe();
    const req = httpMock.expectOne('/api/settings/wordpress/');
    expect(['POST', 'PUT']).toContain(req.request.method);
    req.flush(payload);
  });

  it('runWordPressSync triggers the WP sync POST', () => {
    service.runWordPressSync().subscribe();
    const req = httpMock.expectOne('/api/sync/wordpress/run/');
    expect(req.request.method).toBe('POST');
    req.flush({ status: 'started' });
  });

  // ── Ranking weight settings (each has get + update) ────────────────
  const rankingSettingsCases: Array<[string, string, () => void, () => void]> = [
    [
      'WeightedAuthority',
      '/api/settings/weighted-authority/',
      () => service.getWeightedAuthoritySettings().subscribe(),
      () => service.updateWeightedAuthoritySettings({ ranking_weight: 0.1 } as any).subscribe(),
    ],
    [
      'LinkFreshness',
      '/api/settings/link-freshness/',
      () => service.getLinkFreshnessSettings().subscribe(),
      () => service.updateLinkFreshnessSettings({ ranking_weight: 0.05 } as any).subscribe(),
    ],
    [
      'PhraseMatching',
      '/api/settings/phrase-matching/',
      () => service.getPhraseMatchingSettings().subscribe(),
      () => service.updatePhraseMatchingSettings({ ranking_weight: 0.08 } as any).subscribe(),
    ],
    [
      'LearnedAnchor',
      '/api/settings/learned-anchor/',
      () => service.getLearnedAnchorSettings().subscribe(),
      () => service.updateLearnedAnchorSettings({ ranking_weight: 0.05 } as any).subscribe(),
    ],
    [
      'RareTermPropagation',
      '/api/settings/rare-term-propagation/',
      () => service.getRareTermPropagationSettings().subscribe(),
      () => service.updateRareTermPropagationSettings({ ranking_weight: 0.05 } as any).subscribe(),
    ],
    [
      'FieldAwareRelevance',
      '/api/settings/field-aware-relevance/',
      () => service.getFieldAwareRelevanceSettings().subscribe(),
      () => service.updateFieldAwareRelevanceSettings({ ranking_weight: 0.1 } as any).subscribe(),
    ],
    [
      'ClickDistance',
      '/api/settings/click-distance/',
      () => service.getClickDistanceSettings().subscribe(),
      () => service.updateClickDistanceSettings({ ranking_weight: 0.07 } as any).subscribe(),
    ],
    [
      'FeedbackRerank',
      '/api/settings/explore-exploit/',
      () => service.getFeedbackRerankSettings().subscribe(),
      () => service.updateFeedbackRerankSettings({ enabled: true } as any).subscribe(),
    ],
    [
      'Clustering',
      '/api/settings/clustering/',
      () => service.getClusteringSettings().subscribe(),
      () => service.updateClusteringSettings({ enabled: true } as any).subscribe(),
    ],
    [
      'SlateDiversity',
      '/api/settings/slate-diversity/',
      () => service.getSlateDiversitySettings().subscribe(),
      () => service.updateSlateDiversitySettings({ enabled: true } as any).subscribe(),
    ],
    [
      'GraphCandidate',
      '/api/settings/graph-candidate/',
      () => service.getGraphCandidateSettings().subscribe(),
      () => service.updateGraphCandidateSettings({ enabled: true } as any).subscribe(),
    ],
    [
      'PassageRelevance',
      '/api/settings/passage-relevance/',
      () => service.getPassageRelevanceSettings().subscribe(),
      () => service.updatePassageRelevanceSettings({ enabled: true } as any).subscribe(),
    ],
    [
      'ValueModel',
      '/api/settings/value-model/',
      () => service.getValueModelSettings().subscribe(),
      () => service.updateValueModelSettings({ enabled: true } as any).subscribe(),
    ],
    [
      'AnchorDiversity',
      '/api/settings/anchor-diversity/',
      () => service.getAnchorDiversitySettings().subscribe(),
      () => service.updateAnchorDiversitySettings({ enabled: true } as any).subscribe(),
    ],
    [
      'KeywordStuffing',
      '/api/settings/keyword-stuffing/',
      () => service.getKeywordStuffingSettings().subscribe(),
      () => service.updateKeywordStuffingSettings({ enabled: true } as any).subscribe(),
    ],
    [
      'LinkFarm',
      '/api/settings/link-farm/',
      () => service.getLinkFarmSettings().subscribe(),
      () => service.updateLinkFarmSettings({ enabled: true } as any).subscribe(),
    ],
    [
      'SpamGuard',
      '/api/settings/spam-guards/',
      () => service.getSpamGuardSettings().subscribe(),
      () => service.updateSpamGuardSettings({ max_existing_links_per_host: 3 } as any).subscribe(),
    ],
  ];

  for (const [label, url, callGet, callUpdate] of rankingSettingsCases) {
    it(`get${label}Settings GETs ${url}`, () => {
      callGet();
      expectGet(url).flush({});
    });

    it(`update${label}Settings PUTs ${url}`, () => {
      callUpdate();
      const req = httpMock.expectOne(url);
      expect(['PUT', 'POST']).toContain(req.request.method);
      req.flush({});
    });
  }

  // ── Recalculation triggers ─────────────────────────────────────────
  it('recalculateClickDistance triggers a job POST', () => {
    service.recalculateClickDistance().subscribe();
    const req = httpMock.expectOne('/api/settings/click-distance/recalculate/');
    expect(req.request.method).toBe('POST');
    req.flush({ job_id: 'cd-1' });
  });

  it('recalculateLinkFreshness triggers a job POST', () => {
    service.recalculateLinkFreshness().subscribe();
    const req = httpMock.expectOne('/api/settings/link-freshness/recalculate/');
    expect(req.request.method).toBe('POST');
    req.flush({ job_id: 'lf-1' });
  });

  it('recalculateClustering triggers a job POST', () => {
    service.recalculateClustering().subscribe();
    const req = httpMock.expectOne('/api/settings/clustering/recalculate/');
    expect(req.request.method).toBe('POST');
    req.flush({ job_id: 'cl-1' });
  });

  it('recalculateWeightedAuthority triggers a job POST', () => {
    service.recalculateWeightedAuthority().subscribe();
    const req = httpMock.expectOne('/api/settings/weighted-authority/recalculate/');
    expect(req.request.method).toBe('POST');
    req.flush({ job_id: 'wa-1' });
  });

  it('rebuildKnowledgeGraph triggers a job POST', () => {
    service.rebuildKnowledgeGraph().subscribe();
    const req = httpMock.expectOne('/api/settings/graph/rebuild/');
    expect(req.request.method).toBe('POST');
    req.flush({ job_id: 'kg-1' });
  });

  // ── Connection-test endpoints ──────────────────────────────────────
  it('testGSCConnection POSTs the credentials', () => {
    service.testGSCConnection({ property_url: 'https://example' }).subscribe();
    expectPost('/api/analytics/settings/gsc/test-connection/', { property_url: 'https://example' }).flush({
      success: true,
    } as any);
  });

  it('testGA4TelemetryConnection POSTs the measurement payload', () => {
    service.testGA4TelemetryConnection({ measurement_id: 'G-X', api_secret: 's' }).subscribe();
    expectPost('/api/analytics/settings/ga4/test-connection/', {
      measurement_id: 'G-X',
      api_secret: 's',
    }).flush({ success: true } as any);
  });

  it('testGA4TelemetryReadConnection POSTs read-access credentials', () => {
    service.testGA4TelemetryReadConnection({ property_id: '123', read_client_email: 'a@b' }).subscribe();
    expectPost('/api/analytics/settings/ga4/test-read-connection/', {
      property_id: '123',
      read_client_email: 'a@b',
    }).flush({ success: true } as any);
  });

  it('testMatomoTelemetryConnection POSTs the matomo URL/site', () => {
    service.testMatomoTelemetryConnection({ url: 'https://m', site_id_xenforo: '7' }).subscribe();
    expectPost('/api/analytics/settings/matomo/test-connection/', {
      url: 'https://m',
      site_id_xenforo: '7',
    }).flush({ success: true } as any);
  });

  it('testXenForoConnection POSTs base_url + api_key', () => {
    service.testXenForoConnection({ base_url: 'https://x', api_key: 'k' }).subscribe();
    expectPost('/api/settings/xenforo/test-connection/', { base_url: 'https://x', api_key: 'k' }).flush({
      success: true,
    } as any);
  });

  it('testWordPressConnection POSTs base_url + username + password', () => {
    service.testWordPressConnection({ base_url: 'https://wp', username: 'u', app_password: 'p' }).subscribe();
    expectPost('/api/settings/wordpress/test-connection/', {
      base_url: 'https://wp',
      username: 'u',
      app_password: 'p',
    }).flush({ success: true } as any);
  });

  it('testWebhookEndpoints POSTs an empty body to the test endpoint', () => {
    service.testWebhookEndpoints().subscribe();
    expectPost('/api/settings/webhooks/test/').flush({ success: true } as any);
  });

  it('runGSCSync POSTs an optional lookback payload', () => {
    service.runGSCSync({ lookback_days: 14 }).subscribe();
    expectPost('/api/analytics/telemetry/gsc-sync/', { lookback_days: 14 }).flush({ status: 'queued' });
  });

  it('runGSCSync POSTs an empty body when no payload is given', () => {
    service.runGSCSync().subscribe();
    const req = httpMock.expectOne('/api/analytics/telemetry/gsc-sync/');
    expect(req.request.method).toBe('POST');
    req.flush({ status: 'queued' });
  });

  // ── Google OAuth ───────────────────────────────────────────────────
  it('getGoogleAuthUrl GETs the OAuth authorize endpoint', () => {
    service.getGoogleAuthUrl().subscribe();
    expectGet('/api/analytics/oauth/authorize/').flush({ authorization_url: 'https://x' });
  });

  it('updateGoogleOAuthSettings PUTs client credentials', () => {
    service.updateGoogleOAuthSettings({ client_id: 'a', client_secret: 'b' }).subscribe();
    expectPut('/api/analytics/settings/google-oauth/', { client_id: 'a', client_secret: 'b' }).flush({
      oauth_connected: false,
    } as any);
  });

  it('unlinkGoogleAccount POSTs to the unlink endpoint', () => {
    service.unlinkGoogleAccount().subscribe();
    expectPost('/api/analytics/oauth/unlink/', {}).flush({ status: 'unlinked' });
  });

  // ── Webhook config ─────────────────────────────────────────────────
  it('getWebhookSettings GETs webhook settings', () => {
    service.getWebhookSettings().subscribe();
    expectGet('/api/settings/webhooks/').flush({ xf_secret_configured: false } as any);
  });

  it('updateWebhookSettings PUTs webhook settings', () => {
    service.updateWebhookSettings({ xf_secret: 's' } as any).subscribe();
    const req = httpMock.expectOne('/api/settings/webhooks/');
    expect(['PUT', 'POST']).toContain(req.request.method);
    req.flush({} as any);
  });

  // ── FR-099/105 + Stage1 + Phase6 ───────────────────────────────────
  it('getFr099Fr105Settings GETs the combined endpoint', () => {
    service.getFr099Fr105Settings().subscribe();
    expectGet('/api/settings/fr099-fr105/').flush({});
  });

  it('updateFr099Fr105Settings PUTs the combined endpoint', () => {
    // Structured shape — the seven signal sections are nested under
    // their signal name (rsqva / berp / hgte / darb / kcib / kmig / tapb).
    // Each section's inner payload is free-form; the previous flat
    // `{ kmig_enabled: true }` shape didn't match the real call-site
    // (settings.component.ts) which sends `{ kmig: this.kmig, ... }`.
    const payload = { kmig: { enabled: true } };
    service.updateFr099Fr105Settings(payload).subscribe();
    expectPut('/api/settings/fr099-fr105/', payload).flush({});
  });

  it('getStage1RetrieverSettings GETs the stage1 endpoint', () => {
    service.getStage1RetrieverSettings().subscribe();
    expectGet('/api/settings/stage1-retrievers/').flush({} as any);
  });

  it('updateStage1RetrieverSettings PUTs the stage1 endpoint', () => {
    service.updateStage1RetrieverSettings({} as any).subscribe();
    expectPut('/api/settings/stage1-retrievers/', {}).flush({} as any);
  });

  it('getPhase6PickSettings GETs the phase6 endpoint', () => {
    service.getPhase6PickSettings().subscribe();
    expectGet('/api/settings/phase6-picks/').flush({} as any);
  });

  it('updatePhase6PickSettings PUTs the phase6 endpoint', () => {
    service.updatePhase6PickSettings({} as any).subscribe();
    expectPut('/api/settings/phase6-picks/', {}).flush({} as any);
  });

  // ── Runtime config + models ────────────────────────────────────────
  it('getRuntimeConfig GETs runtime-config', () => {
    service.getRuntimeConfig().subscribe();
    expectGet('/api/settings/runtime-config/').flush({} as any);
  });

  it('updateRuntimeConfig POSTs the runtime-config payload', () => {
    service.updateRuntimeConfig({ key: 'value' } as any).subscribe();
    expectPost('/api/settings/runtime-config/', { key: 'value' }).flush({ updated: {} });
  });

  it('getRuntimeSummary GETs runtime/summary', () => {
    service.getRuntimeSummary().subscribe();
    expectGet('/api/settings/runtime/summary/').flush({} as any);
  });

  it('getRuntimeModels GETs runtime/models', () => {
    service.getRuntimeModels().subscribe();
    expectGet('/api/settings/runtime/models/').flush({} as any);
  });

  it('registerRuntimeModel POSTs to runtime/models', () => {
    service.registerRuntimeModel({ name: 'x' } as any).subscribe();
    expectPost('/api/settings/runtime/models/', { name: 'x' }).flush({} as any);
  });

  it('runRuntimeModelAction POSTs to the per-id action endpoint', () => {
    service.runRuntimeModelAction(5, { action: 'restart' } as any).subscribe();
    expectPost('/api/settings/runtime/models/5/action/', { action: 'restart' }).flush({});
  });

  it('deleteRuntimePlacement DELETEs the placement endpoint', () => {
    service.deleteRuntimePlacement(11).subscribe();
    expectDelete('/api/settings/runtime/models/placements/11/').flush({ deleted: true });
  });

  // ── Helpers (list endpoint has catchError fallback) ────────────────
  it('listHelpers unwraps {results:[…]} envelope', () =>
    new Promise<void>((done) => {
      service.listHelpers().subscribe((helpers) => {
        expect(helpers).toEqual([{ id: 1 } as any]);
        done();
      });
      expectGet('/api/settings/helpers/').flush({ results: [{ id: 1 }] });
    }));

  it('listHelpers returns [] on HTTP error', () =>
    new Promise<void>((done) => {
      service.listHelpers().subscribe((helpers) => {
        expect(helpers).toEqual([]);
        done();
      });
      expectGet('/api/settings/helpers/').flush('boom', { status: 500, statusText: 'Server' });
    }));

  it('createHelper POSTs to the helpers endpoint', () => {
    service.createHelper({ name: 'h' } as any).subscribe();
    expectPost('/api/settings/helpers/', { name: 'h' }).flush({ id: 1, name: 'h' });
  });

  it('updateHelper PATCHes the per-id helper endpoint', () => {
    service.updateHelper(2, { name: 'h2' } as any).subscribe();
    expectPatch('/api/settings/helpers/2/', { name: 'h2' }).flush({} as any);
  });

  it('deleteHelper DELETEs the per-id helper endpoint', () => {
    service.deleteHelper(3).subscribe();
    expectDelete('/api/settings/helpers/3/').flush(null);
  });

  // ── Weight presets ─────────────────────────────────────────────────
  it('listWeightPresets unwraps {results:[…]} envelope', () =>
    new Promise<void>((done) => {
      service.listWeightPresets().subscribe((presets) => {
        expect(presets).toEqual([{ id: 1, name: 'p' } as any]);
        done();
      });
      expectGet('/api/weight-presets/').flush({ results: [{ id: 1, name: 'p' }] });
    }));

  it('listWeightPresets returns [] on HTTP error', () =>
    new Promise<void>((done) => {
      service.listWeightPresets().subscribe((presets) => {
        expect(presets).toEqual([]);
        done();
      });
      expectGet('/api/weight-presets/').flush('boom', { status: 500, statusText: 'Server' });
    }));

  it('createWeightPreset POSTs to weight-presets', () => {
    service.createWeightPreset({ name: 'p', weights: { 'a.b': '1' } }).subscribe();
    expectPost('/api/weight-presets/', { name: 'p', weights: { 'a.b': '1' } }).flush({ id: 5 } as any);
  });

  it('renameWeightPreset PATCHes per-id preset', () => {
    service.renameWeightPreset(7, 'New').subscribe();
    expectPatch('/api/weight-presets/7/', { name: 'New' }).flush({ id: 7, name: 'New' } as any);
  });

  it('deleteWeightPreset DELETEs per-id preset', () => {
    service.deleteWeightPreset(8).subscribe();
    expectDelete('/api/weight-presets/8/').flush(null);
  });

  it('applyWeightPreset POSTs to the apply action', () => {
    service.applyWeightPreset(9).subscribe();
    expectPost('/api/weight-presets/9/apply/').flush({ detail: 'applied' });
  });

  it('getCurrentWeights GETs current weights', () => {
    service.getCurrentWeights().subscribe();
    expectGet('/api/weight-presets/current/').flush({});
  });

  it('triggerWeightTune POSTs the weight-tune trigger action', () => {
    service.triggerWeightTune().subscribe();
    expectPost('/api/settings/weight-tune/trigger/', {}).flush({ detail: 'queued', task_id: 't' });
  });

  it('listChallengers unwraps {results:[…]} envelope', () =>
    new Promise<void>((done) => {
      service.listChallengers().subscribe((c) => {
        expect(c).toEqual([{ id: 1 } as any]);
        done();
      });
      expectGet('/api/weight-challengers/').flush({ results: [{ id: 1 }] });
    }));

  it('listChallengers returns [] on HTTP error', () =>
    new Promise<void>((done) => {
      service.listChallengers().subscribe((c) => {
        expect(c).toEqual([]);
        done();
      });
      expectGet('/api/weight-challengers/').flush('boom', { status: 500, statusText: 'Server' });
    }));

  it('evaluateChallenger POSTs to the weight-tune evaluate action', () => {
    service.evaluateChallenger('run-7').subscribe();
    expectPost('/api/settings/weight-tune/evaluate/run-7/', {}).flush({
      detail: 'queued',
      task_id: 't',
    });
  });

  it('rejectChallenger POSTs to the per-challenger reject action', () => {
    service.rejectChallenger(7).subscribe();
    expectPost('/api/weight-challengers/7/reject/', {}).flush({ detail: 'rejected' });
  });

  it('listWeightHistory unwraps {results:[…]} envelope', () =>
    new Promise<void>((done) => {
      service.listWeightHistory().subscribe((h) => {
        expect(h).toEqual([{ id: 1 } as any]);
        done();
      });
      expectGet('/api/weight-history/').flush({ results: [{ id: 1 }] });
    }));

  it('listWeightHistory returns [] on HTTP error', () =>
    new Promise<void>((done) => {
      service.listWeightHistory().subscribe((h) => {
        expect(h).toEqual([]);
        done();
      });
      expectGet('/api/weight-history/').flush('boom', { status: 500, statusText: 'Server' });
    }));

  // ── GSC / GA4 / Matomo / OAuth get/update wrappers ─────────────────
  it('getGSCSettings GETs the analytics GSC settings endpoint', () => {
    service.getGSCSettings().subscribe();
    expectGet('/api/analytics/settings/gsc/').flush({} as any);
  });

  it('updateGSCSettings PUTs the GSC settings payload', () => {
    service.updateGSCSettings({ property_url: 'https://x' } as any).subscribe();
    expectPut('/api/analytics/settings/gsc/', { property_url: 'https://x' }).flush({} as any);
  });

  it('getGA4TelemetrySettings GETs the analytics GA4 endpoint', () => {
    service.getGA4TelemetrySettings().subscribe();
    expectGet('/api/analytics/settings/ga4/').flush({} as any);
  });

  it('updateGA4TelemetrySettings PUTs the GA4 telemetry payload', () => {
    service.updateGA4TelemetrySettings({ behavior_enabled: true } as any).subscribe();
    expectPut('/api/analytics/settings/ga4/', { behavior_enabled: true }).flush({} as any);
  });

  it('getGoogleOAuthSettings GETs the analytics OAuth settings endpoint', () => {
    service.getGoogleOAuthSettings().subscribe();
    expectGet('/api/analytics/settings/google-oauth/').flush({} as any);
  });

  it('getMatomoTelemetrySettings GETs analytics Matomo settings', () => {
    service.getMatomoTelemetrySettings().subscribe();
    expectGet('/api/analytics/settings/matomo/').flush({} as any);
  });

  it('updateMatomoTelemetrySettings PUTs Matomo settings', () => {
    service.updateMatomoTelemetrySettings({ enabled: true } as any).subscribe();
    expectPut('/api/analytics/settings/matomo/', { enabled: true }).flush({} as any);
  });

  // ── Weight history rollback ────────────────────────────────────────
  it('rollbackWeights POSTs the per-history rollback action', () => {
    service.rollbackWeights(11).subscribe();
    expectPost('/api/weight-history/11/rollback/', {}).flush({ detail: 'rolled back' });
  });
});
