import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { EMPTY } from 'rxjs';

import { EmbeddingsComponent } from './embeddings.component';
import { VisibilityGateService } from '../core/util/visibility-gate.service';

const STATUS = {
  active_provider: 'openai',
  fallback_provider: 'openai',
  model_name: 'text-embedding-3-small',
  signature: 'sig-1',
  dimension: 1024,
  max_tokens: 512,
  hardware: { tier: 'mid', ram_gb: 16, cpu_cores: 8, recommended_batch_size: 16 },
  coverage: { total: 100, embedded: 50, pct: 0.5 },
  spend_this_month: [],
  recommended_provider: 'openai',
};

describe('EmbeddingsComponent', () => {
  let fixture: ComponentFixture<EmbeddingsComponent>;
  let component: EmbeddingsComponent;
  let httpMock: HttpTestingController;

  function flushInitial(): void {
    httpMock.expectOne('/api/embedding/status/').flush(STATUS);
    httpMock.expectOne('/api/embedding/settings/').flush({ 'embedding.model': 'text-embedding-3-small' });
    httpMock.expectOne('/api/embedding/bakeoff/').flush([]);
    httpMock.expectOne('/api/embedding/gate-decisions/').flush([]);
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EmbeddingsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: VisibilityGateService, useValue: { whileLoggedInAndVisible: () => EMPTY } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(EmbeddingsComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('renders without throwing and loads status + settings on init', () => {
    fixture.detectChanges();
    flushInitial();
    expect(component).toBeTruthy();
    expect(component.status()?.active_provider).toBe('openai');
    expect(component.settings()['embedding.model']).toBe('text-embedding-3-small');
  });

  it('applyProviderChange POSTs to provider endpoint and reloads status', () => {
    fixture.detectChanges();
    flushInitial();
    // The active provider seeded from STATUS is 'openai'; switching to a
    // DIFFERENT provider is what actually fires the POST. Selecting the same
    // provider is a deliberate no-op (the early-return guard in
    // applyProviderChange), so the test must pick another provider.
    component.pendingProvider = 'gemini';
    component.applyProviderChange();

    const post = httpMock.expectOne('/api/embedding/provider/');
    expect(post.request.method).toBe('POST');
    expect(post.request.body).toEqual({ name: 'gemini' });
    post.flush({ ok: true });

    httpMock.expectOne('/api/embedding/status/').flush(STATUS);
    expect(component.busyAction()).toBeNull();
  });

  it('handles status load failure without crashing', () => {
    fixture.detectChanges();
    spyOn(console, 'error');
    httpMock.expectOne('/api/embedding/status/').flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    httpMock.expectOne('/api/embedding/settings/').flush({});
    httpMock.expectOne('/api/embedding/bakeoff/').flush([]);
    httpMock.expectOne('/api/embedding/gate-decisions/').flush([]);
    expect(component.loading()).toBeFalse();
    expect(console.error).toHaveBeenCalled();
  });

  it('toggleApiKey flips the showApiKey signal', () => {
    fixture.detectChanges();
    flushInitial();
    expect(component.showApiKey()).toBeFalse();
    component.toggleApiKey();
    expect(component.showApiKey()).toBeTrue();
  });
});
