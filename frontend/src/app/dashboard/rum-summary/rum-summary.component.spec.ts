import { ComponentFixture, TestBed, discardPeriodicTasks, fakeAsync, tick } from '@angular/core/testing';
import { RumSummaryComponent } from './rum-summary.component';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

describe('RumSummaryComponent', () => {
  let component: RumSummaryComponent;
  let fixture: ComponentFixture<RumSummaryComponent>;
  let httpMock: HttpTestingController;
  let visibilityGate: jasmine.SpyObj<VisibilityGateService>;

  beforeEach(async () => {
    visibilityGate = jasmine.createSpyObj('VisibilityGateService', ['whileLoggedInAndVisible']);
    visibilityGate.whileLoggedInAndVisible.and.callFake((fn) => fn());

    await TestBed.configureTestingModule({
      imports: [
        HttpClientTestingModule,
        MatCardModule,
        MatIconModule,
        MatProgressSpinnerModule,
        RumSummaryComponent
      ],
      providers: [
        { provide: VisibilityGateService, useValue: visibilityGate }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(RumSummaryComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    flushExtraPolls();
    httpMock.verify();
  });

  function flushExtraPolls(): void {
    httpMock.match('/api/rum/summary/').forEach((req) => {
      req.flush({ window_hours: 24, metrics: {}, routes: {} });
    });
  }

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should fetch and display RUM summary', fakeAsync(() => {
    const mockSummary = {
      window_hours: 24,
      metrics: {
        LCP: { p50: 2000, p75: 2200, p95: 2500, n: 100 },
        INP: { p50: 100, p75: 150, p95: 200, n: 100 },
        CLS: { p50: 0.05, p75: 0.08, p95: 0.12, n: 100 },
        FCP: { p50: 1500, p75: 1700, p95: 1900, n: 100 },
        TTFB: { p50: 500, p75: 600, p95: 800, n: 100 }
      },
      routes: {}
    };

    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/rum/summary/');
    req.flush(mockSummary);
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.rs-row');
    expect(rows.length).toBe(5);
    expect(rows[0].textContent).toContain('LCP');
    expect(rows[0].textContent).toContain('2,200'); // Decimal pipe formatting
    flushExtraPolls();
    discardPeriodicTasks();
  }));

  it('should show empty state if no samples', fakeAsync(() => {
    const mockSummary = {
      window_hours: 24,
      metrics: {
        LCP: { p50: 0, p75: 0, p95: 0, n: 0 }
      },
      routes: {}
    };

    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/rum/summary/');
    req.flush(mockSummary);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.rs-empty').textContent).toContain('No real-user samples yet');
    flushExtraPolls();
    discardPeriodicTasks();
  }));

  it('should handle error gracefully', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/rum/summary/');
    req.error(new ErrorEvent('Network error'));
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.rs-empty').textContent).toContain('Could not load RUM summary');
    flushExtraPolls();
    discardPeriodicTasks();
  }));
});
