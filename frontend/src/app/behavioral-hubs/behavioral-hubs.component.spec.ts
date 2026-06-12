import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of, throwError } from 'rxjs';

import { BehavioralHubsComponent } from './behavioral-hubs.component';
import { BehavioralHubService } from './behavioral-hub.service';

const stubHub = {
  hub_id: 'h1',
  name: 'Hub One',
  detection_method: 'manual' as const,
  min_jaccard_used: 0,
  member_count: 2,
  auto_link_enabled: true,
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-02T00:00:00Z',
};

describe('BehavioralHubsComponent', () => {
  let fixture: ComponentFixture<BehavioralHubsComponent>;
  let component: BehavioralHubsComponent;
  let httpMock: HttpTestingController;
  const svcStub = {
    getHubs: () => of({ count: 1, results: [stubHub] }),
    getRuns: () => of([]),
    getSettings: () => of(null),
    getHub: () => of({ ...stubHub, members: [] }),
    patchHub: (_: string, body: { name?: string; auto_link_enabled?: boolean }) =>
      of({ ...stubHub, ...body }),
    removeMember: () => of({}),
    triggerCompute: () => of({ ok: true }),
    triggerDetection: () => of({ ok: true }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [BehavioralHubsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: BehavioralHubService, useValue: svcStub },
      ],
    })
      .overrideComponent(BehavioralHubsComponent, {
        set: { template: '<div></div>' },
      })
      .compileComponents();
    fixture = TestBed.createComponent(BehavioralHubsComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('renders and loads the hub list on init', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((r) => r.flush({}));
    expect(component.hubs().length).toBe(1);
    expect(component.totalHubs()).toBe(1);
    expect(component.membershipLabel('auto_detected')).toBe('Auto');
  });

  it('opens a hub and surfaces it in selectedHub', () => {
    fixture.detectChanges();
    component.openHub(stubHub);
    expect(component.selectedHub()?.hub_id).toBe('h1');
    expect(component.editName).toBe('Hub One');
  });

  it('handles error from getHubs without throwing', () => {
    const failing = {
      ...svcStub,
      getHubs: () => throwError(() => new Error('boom')),
    };
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [BehavioralHubsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: BehavioralHubService, useValue: failing },
      ],
    }).overrideComponent(BehavioralHubsComponent, {
      set: { template: '<div></div>' },
    });
    const fx = TestBed.createComponent(BehavioralHubsComponent);
    fx.detectChanges();
    expect(fx.componentInstance.loadingHubs()).toBe(false);
    expect(fx.componentInstance.hubs().length).toBe(0);
  });
});
