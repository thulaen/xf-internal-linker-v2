import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of, throwError } from 'rxjs';

import { PerformanceComponent } from './performance.component';
import { PerformanceService } from './performance.service';

const stubRun = {
  id: 1,
  started_at: '2026-04-30T11:00:00Z',
  finished_at: '2026-04-30T11:05:00Z',
  trigger: 'manual' as const,
  status: 'completed' as const,
  summary_json: { total: 3, fast: 2, ok: 1, slow: 0, languages: { cpp: 2, python: 1 } },
  results: [
    { id: 1, language: 'cpp', extension: 'extA', function_name: 'foo', input_size: 'small', mean_ns: 100, median_ns: 100, items_per_second: 1, status: 'fast' as const, threshold_ns: null },
  ],
};

describe('PerformanceComponent', () => {
  let fixture: ComponentFixture<PerformanceComponent>;
  let component: PerformanceComponent;
  let httpMock: HttpTestingController;
  const svcStub = {
    getLatest: () => of(stubRun),
    getTrends: () => of([]),
    getStage2PathStatus: () => of(null),
    trigger: () => of({ run_id: 2 }),
    getReport: () => of({ report: 'x' }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PerformanceComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: PerformanceService, useValue: svcStub },
      ],
    })
      .overrideComponent(PerformanceComponent, {
        set: { template: '<div></div>' },
      })
      .compileComponents();
    fixture = TestBed.createComponent(PerformanceComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('loads the latest run and computes summary counts', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((r) => r.flush({}));
    expect(component.latestRun()?.id).toBe(1);
    expect(component.fastCount()).toBe(2);
    expect(component.slowCount()).toBe(0);
    expect(component.uniqueFunctions().length).toBe(1);
  });

  it('toggles language filter and reflects in filteredResults', () => {
    fixture.detectChanges();
    component.filterByLanguage('cpp');
    expect(component.selectedLanguage()).toBe('cpp');
    expect(component.filteredResults().length).toBe(1);
    component.filterByLanguage('cpp');
    expect(component.selectedLanguage()).toBe('all');
  });

  it('shows error message when getLatest fails', () => {
    const failing = { ...svcStub, getLatest: () => throwError(() => new Error('x')) };
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [PerformanceComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: PerformanceService, useValue: failing },
      ],
    }).overrideComponent(PerformanceComponent, {
      set: { template: '<div></div>' },
    });
    const fx = TestBed.createComponent(PerformanceComponent);
    fx.detectChanges();
    expect(fx.componentInstance.errorMessage()).toContain('No benchmark data');
  });
});
