import { ComponentFixture, TestBed, fakeAsync, tick, discardPeriodicTasks } from '@angular/core/testing';
import { SystemMetricsComponent } from './system-metrics.component';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { Observable } from 'rxjs';

describe('SystemMetricsComponent', () => {
  let component: SystemMetricsComponent;
  let fixture: ComponentFixture<SystemMetricsComponent>;
  let httpMock: HttpTestingController;

  const mockMetrics = {
    cpu_percent: 50,
    ram_percent: 60,
    ram_used_mb: 8192,
    ram_total_mb: 16384,
  };

  beforeEach(async () => {
    const mockVisibility = createSpyObj(['whileLoggedInAndVisible']);
    // Immediate execution of the polling logic
    mockVisibility.whileLoggedInAndVisible.mockImplementation((fn: () => Observable<unknown>) => fn());

    await TestBed.configureTestingModule({
      imports: [SystemMetricsComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: VisibilityGateService, useValue: mockVisibility }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(SystemMetricsComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    fixture.destroy();
    // Match any lingering requests to satisfy verify()
    httpMock.match('/api/system/metrics/');
    httpMock.verify();
  });

  it('should create', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/system/metrics/');
    req.flush(mockMetrics);
    expect(component).toBeTruthy();
    discardPeriodicTasks();
  }));

  it('should fetch metrics on init', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/system/metrics/');
    req.flush(mockMetrics);
    fixture.detectChanges();
    
    expect(component.metrics()).toEqual(mockMetrics);
    expect(fixture.nativeElement.querySelector('.meter-value').textContent).toContain('50%');
    discardPeriodicTasks();
  }));

  it('should show tip for high RAM usage', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/system/metrics/');
    req.flush({ ...mockMetrics, ram_percent: 95 });
    fixture.detectChanges();
    
    expect(component.tip()).toContain('Memory is almost full');
    expect(fixture.nativeElement.querySelector('.suggestion-tip')).toBeTruthy();
    discardPeriodicTasks();
  }));

  it('should determine correct tint and bar color', () => {
    expect(component.tintClass(90)).toBe('tint-hot');
    expect(component.tintClass(70)).toBe('tint-warn');
    expect(component.tintClass(50)).toBe('tint-ok');
    
    expect(component.barColor(90)).toBe('warn');
    expect(component.barColor(70)).toBe('accent');
    expect(component.barColor(50)).toBe('primary');
  });
});
