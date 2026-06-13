import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';

import { SiloArchitectureTabComponent } from './silo-architecture-tab.component';
import { ScopeItem, SiloGroup, SiloSettings } from '../silo-settings.service';

const DEFAULT_SETTINGS: SiloSettings = {
  mode: 'prefer_same_silo',
  same_silo_boost: 0.1,
  cross_silo_penalty: 0.1,
};

const SAMPLE_GROUPS: SiloGroup[] = [
  {
    id: 1,
    name: 'Technology',
    slug: 'tech',
    description: '',
    display_order: 0,
    scope_count: 2,
    created_at: '2026-05-10T00:00:00Z',
    updated_at: '2026-05-10T00:00:00Z',
  },
];

const SAMPLE_SCOPES: ScopeItem[] = [
  {
    id: 10,
    scope_id: 100,
    scope_type: 'category',
    scope_type_label: 'Category',
    source_label: 'wp',
    title: 'Tech Posts',
    parent: null,
    parent_title: null,
    silo_group: 1,
    silo_group_name: 'Technology',
    is_enabled: true,
    content_count: 12,
    display_order: 0,
  },
  {
    id: 11,
    scope_id: 101,
    scope_type: 'category',
    scope_type_label: 'Category',
    source_label: 'wp',
    title: 'News Posts',
    parent: null,
    parent_title: null,
    silo_group: null,
    silo_group_name: '',
    is_enabled: true,
    content_count: 7,
    display_order: 1,
  },
];

describe('SiloArchitectureTabComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SiloArchitectureTabComponent, NoopAnimationsModule],
      providers: [provideHttpClient(withXhr()), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  function flushInitialLoad(): void {
    httpMock.expectOne('/api/settings/silos/').flush(DEFAULT_SETTINGS);
    httpMock.expectOne('/api/silo-groups/').flush(SAMPLE_GROUPS);
    httpMock.expectOne('/api/scopes/').flush(SAMPLE_SCOPES);
  }

  it('renders the four silo cards without error', () => {
    const fixture = TestBed.createComponent(SiloArchitectureTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const root: HTMLElement = fixture.nativeElement;
    expect(root.querySelector('#silo-settings')).not.toBeNull();
    expect(root.querySelector('#settings-create-silo-group')).not.toBeNull();
    expect(root.querySelector('#silo-groups')).not.toBeNull();
    expect(root.querySelector('#scope-assignments')).not.toBeNull();
  });

  it('sends PUT to /api/settings/silos/ with the current payload on save', () => {
    const fixture = TestBed.createComponent(SiloArchitectureTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    cmp.settings.same_silo_boost = 0.15;
    cmp.saveSettings();

    const req = httpMock.expectOne('/api/settings/silos/');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.same_silo_boost).toBe(0.15);
    expect(req.request.body.mode).toBe('prefer_same_silo');
    req.flush({ ...DEFAULT_SETTINGS, same_silo_boost: 0.15 });

    expect(cmp.savingSilo()).toBe(false);
  });

  it('derives assignedScopeCount from loaded scopes', () => {
    const fixture = TestBed.createComponent(SiloArchitectureTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    // Two sample scopes; one assigned (silo_group=1), one unassigned (null).
    expect(cmp.scopes.length).toBe(2);
    expect(cmp.assignedScopeCount).toBe(1);
  });

  it('emits dirtyChanged true after a state change and false after a successful save', () => {
    const fixture = TestBed.createComponent(SiloArchitectureTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    const emitted: boolean[] = [];
    cmp.dirtyChanged.subscribe((v) => emitted.push(v));

    cmp.markDirty();
    expect(emitted).toEqual([true]);

    cmp.saveSettings();
    httpMock.expectOne('/api/settings/silos/').flush(DEFAULT_SETTINGS);

    expect(emitted).toEqual([true, false]);
  });
});
