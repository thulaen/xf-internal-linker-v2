import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Subject } from 'rxjs';

import { OperationsFeedComponent } from './operations-feed.component';
import { OpsEvent } from './ops-feed.types';
import { RealtimeService } from '../core/services/realtime.service';

function evt(over: Partial<OpsEvent> = {}): OpsEvent {
  return {
    id: 1,
    timestamp: new Date().toISOString(),
    severity: 'info',
    source: 'pipeline',
    event_type: 'pipeline.run',
    plain_english: 'Pipeline started.',
    related_entity_type: '',
    related_entity_id: '',
    runtime_context: {},
    occurrence_count: 1,
    error_log_id: null,
    ...over,
  };
}

describe('OperationsFeedComponent', () => {
  let fixture: ComponentFixture<OperationsFeedComponent>;
  let component: OperationsFeedComponent;
  let httpMock: HttpTestingController;
  let realtime$: Subject<{ payload: OpsEvent }>;

  beforeEach(async () => {
    realtime$ = new Subject();
    await TestBed.configureTestingModule({
      imports: [OperationsFeedComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: RealtimeService, useValue: { subscribeTopic: () => realtime$.asObservable() } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(OperationsFeedComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('hydrates events from REST on init', () => {
    fixture.detectChanges();
    const rows = [evt({ id: 2 }), evt({ id: 1 })];
    httpMock.expectOne('/api/operations/events/?limit=500').flush(rows);
    expect(component).toBeTruthy();
    // Component reverses server response (newest-last).
    const rendered = (component as unknown as { events: () => OpsEvent[] }).events();
    expect(rendered[rendered.length - 1].id).toBe(2);
  });

  it('togglePause buffers incoming events and flushes on resume', () => {
    fixture.detectChanges();
    httpMock.expectOne('/api/operations/events/?limit=500').flush([]);
    const c = component as unknown as {
      paused: () => boolean;
      togglePause: () => void;
      buffered: () => OpsEvent[];
      events: () => OpsEvent[];
    };
    c.togglePause();
    expect(c.paused()).toBeTrue();
    realtime$.next({ payload: evt({ id: 99 }) });
    expect(c.buffered().length).toBe(1);
    c.togglePause();
    expect(c.events().some((e) => e.id === 99)).toBeTrue();
    expect(c.buffered().length).toBe(0);
  });

  it('handles initial REST load failure gracefully', () => {
    fixture.detectChanges();
    httpMock.expectOne('/api/operations/events/?limit=500')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    expect(component).toBeTruthy();
    const rendered = (component as unknown as { events: () => OpsEvent[] }).events();
    expect(rendered.length).toBe(0);
  });
});
