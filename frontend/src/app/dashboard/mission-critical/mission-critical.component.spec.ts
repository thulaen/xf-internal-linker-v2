import { ComponentFixture, TestBed, fakeAsync, tick, flushMicrotasks, discardPeriodicTasks } from '@angular/core/testing';
import { MissionCriticalComponent } from './mission-critical.component';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { RealtimeService } from '../../core/services/realtime.service';
import { ScrollAttentionService } from '../../core/services/scroll-attention.service';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialogModule } from '@angular/material/dialog';
import { Subject } from 'rxjs';
import { McPayload } from './mc-types';

describe('MissionCriticalComponent', () => {
  let component: MissionCriticalComponent;
  let fixture: ComponentFixture<MissionCriticalComponent>;
  let httpMock: HttpTestingController;
  let realtimeMock: SpyObj<RealtimeService>;
  let scrollMock: SpyObj<ScrollAttentionService>;
  let realtimeSubject: Subject<any>;

  const mockPayload: McPayload = {
    updated_at: new Date().toISOString(),
    tiles: [
      {
        id: 'pipeline',
        name: 'Pipeline',
        state: 'WORKING',
        plain_english: 'All systems operational.',
        last_action_at: null,
        progress: 85,
        actions: ['Restart'],
        group: null,
        root_cause: null
      },
      {
        id: 'signals',
        name: 'Signals',
        state: 'FAILED',
        plain_english: 'Critical signal failure detected.',
        last_action_at: null,
        progress: null,
        actions: ['Repair'],
        group: null,
        root_cause: null
      }
    ]
  };

  beforeEach(async () => {
    realtimeSubject = new Subject();
    realtimeMock = createSpyObj(['subscribeTopic']);
    realtimeMock.subscribeTopic.mockReturnValue(realtimeSubject);
    scrollMock = createSpyObj(['drawTo']);

    await TestBed.configureTestingModule({
      imports: [
        MissionCriticalComponent,
        HttpClientTestingModule,
        NoopAnimationsModule,
        MatSnackBarModule,
        MatDialogModule
      ],
      providers: [
        { provide: RealtimeService, useValue: realtimeMock },
        { provide: ScrollAttentionService, useValue: scrollMock }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(MissionCriticalComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    // Clear any leftover matching requests to satisfy verify()
    httpMock.match('/api/system/status/mission-critical/');
    httpMock.verify();
  });

  it('should create and load initial tiles', fakeAsync(() => {
    fixture.detectChanges();
    tick(500); // Handle throttleTime(300) with leading: true, trailing: true
    
    const reqs = httpMock.match('/api/system/status/mission-critical/');
    expect(reqs.length).toBeGreaterThanOrEqual(1);
    // Flush the last one (active), previous are cancelled by switchMap
    reqs[reqs.length - 1].flush(mockPayload);
    
    fixture.detectChanges();
    tick(); // Handle queueMicrotask in flashNewFailures

    expect(component['tiles']().length).toBe(2);
    expect(fixture.nativeElement.querySelector('.mc-summary-title').textContent).toContain('Mission Critical');
    discardPeriodicTasks();
  }));

  it('should trigger scroll attention on new failures', fakeAsync(() => {
    fixture.detectChanges();
    tick(500);
    
    const reqs = httpMock.match('/api/system/status/mission-critical/');
    reqs[reqs.length - 1].flush(mockPayload);
    
    fixture.detectChanges();
    
    // Flush any microtasks (like queueMicrotask in flashNewFailures)
    flushMicrotasks();

    expect(scrollMock.drawTo).toHaveBeenCalledWith('#mc-tile-signals', expect.objectContaining({ priority: 'urgent' }));
    discardPeriodicTasks();
  }));

  it('should refresh on realtime nudge', fakeAsync(() => {
    fixture.detectChanges();
    tick(500);
    
    let reqs = httpMock.match('/api/system/status/mission-critical/');
    reqs[reqs.length - 1].flush(mockPayload);

    realtimeSubject.next({ type: 'mission_critical', payload: {} });
    tick(500); // Handle throttleTime(300)

    reqs = httpMock.match('/api/system/status/mission-critical/');
    expect(reqs.length).toBe(1);
    reqs[0].flush(mockPayload);
    fixture.detectChanges();
    discardPeriodicTasks();
  }));

  it('should format timestamps correctly', () => {
    fixture.detectChanges(); // Sync call, but triggers async stream
    // No tick(500) here, so match(0) is fine
    const reqs = httpMock.match('/api/system/status/mission-critical/');
    // If leading: true, it might have fired one.
    if (reqs.length > 0) reqs.forEach(r => r.flush(mockPayload));
    
    expect(component.relative(new Date().toISOString())).toBe('just now');
  });

  it('should format relative timestamps correctly', () => {
    const now = new Date();
    const fiveMinAgo = new Date(now.getTime() - 5 * 60 * 1000).toISOString();
    expect(component.relative(fiveMinAgo)).toBe('5m ago');
    
    const justNow = new Date(now.getTime() - 2000).toISOString();
    expect(component.relative(justNow)).toBe('just now');
  });
});
