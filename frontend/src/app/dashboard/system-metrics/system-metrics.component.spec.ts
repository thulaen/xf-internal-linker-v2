import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { SystemMetricsComponent } from './system-metrics.component';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('SystemMetricsComponent', () => {
  let component: SystemMetricsComponent;
  let fixture: ComponentFixture<SystemMetricsComponent>;
  let httpMock: HttpTestingController;
  let mockVisibility: jasmine.SpyObj<VisibilityGateService>;

  const mockMetrics = {
    cpu_percent: 50,
    ram_used_mb: 8000,
    ram_total_mb: 16000,
    ram_percent: 50,
    gpu: {
      available: true,
      temp_c: 60,
      vram_used_mb: 2000,
      vram_total_mb: 8000,
      vram_percent: 25,
      utilization_pct: 10
    }
  };

  beforeEach(async () => {
    mockVisibility = jasmine.createSpyObj('VisibilityGateService', ['whileLoggedInAndVisible']);
    mockVisibility.whileLoggedInAndVisible.and.callFake((fn) => fn());

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
    httpMock.verify();
  });

  it('should create', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/system/metrics/');
    req.flush(mockMetrics);
    expect(component).toBeTruthy();
  }));

  it('should fetch metrics on init', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/system/metrics/');
    req.flush(mockMetrics);
    fixture.detectChanges();
    
    expect(component.metrics()).toEqual(mockMetrics);
    expect(fixture.nativeElement.querySelector('.meter-value').textContent).toContain('50%');
  }));

  it('should show GPU section if available', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/system/metrics/');
    req.flush(mockMetrics);
    fixture.detectChanges();
    
    expect(fixture.nativeElement.querySelector('.meter-row:nth-child(3)')).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('GPU memory');
  }));

  it('should show info if GPU is unavailable', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/system/metrics/');
    req.flush({ ...mockMetrics, gpu: { available: false } });
    fixture.detectChanges();
    
    expect(fixture.nativeElement.querySelector('.gpu-unavailable')).toBeTruthy();
  }));

  it('should show tip for high RAM usage', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const req = httpMock.expectOne('/api/system/metrics/');
    req.flush({ ...mockMetrics, ram_percent: 95 });
    fixture.detectChanges();
    
    expect(component.tip()).toContain('Memory is almost full');
    expect(fixture.nativeElement.querySelector('.suggestion-tip')).toBeTruthy();
  }));

  it('should determine correct tint and bar color', () => {
    expect(component.tintClass(90)).toBe('tint-hot');
    expect(component.tintClass(70)).toBe('tint-warn');
    expect(component.tintClass(30)).toBe('tint-ok');
    
    expect(component.barColor(90)).toBe('warn');
    expect(component.barColor(70)).toBe('accent');
    expect(component.barColor(30)).toBe('primary');
  });
});
