import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { MatSnackBar } from '@angular/material/snack-bar';
import { of, throwError } from 'rxjs';

import { MonthlyReportsComponent } from './monthly-reports.component';
import { McpService } from '../core/services/mcp.service';

describe('MonthlyReportsComponent', () => {
  let fixture: ComponentFixture<MonthlyReportsComponent>;
  let component: MonthlyReportsComponent;
  let httpMock: HttpTestingController;
  const snackStub = { open: () => undefined };
  const svcStub = {
    listMonthlyReports: () =>
      of({
        reports: [
          { month: '2026-04', filename: 'monthly-2026-04.md', size_bytes: 100, modified_at: '2026-04-30T00:00:00Z' },
        ],
      }),
    readMonthlyReport: () =>
      of({ month: '2026-04', filename: 'monthly-2026-04.md', body: '# hello' }),
    runMonthly: () => of({ month: '2026-04', strategy: 'top50' }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MonthlyReportsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: McpService, useValue: svcStub },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    })
      .overrideComponent(MonthlyReportsComponent, {
        set: { template: '<div></div>' },
      })
      .compileComponents();
    fixture = TestBed.createComponent(MonthlyReportsComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('renders and auto-selects the first report on init', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((r) => r.flush({}));
    expect(component.reports()?.length).toBe(1);
    expect(component.selectedMonth()).toBe('2026-04');
    expect(component.selectedBody()?.body).toContain('hello');
  });

  it('runNow toggles the busy flag and resolves', () => {
    fixture.detectChanges();
    component.runNow();
    expect(component.runBusy()).toBeFalse();
  });

  it('handles error from listMonthlyReports', () => {
    const failing = {
      ...svcStub,
      listMonthlyReports: () => throwError(() => ({ message: 'nope' })),
    };
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [MonthlyReportsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: McpService, useValue: failing },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    }).overrideComponent(MonthlyReportsComponent, {
      set: { template: '<div></div>' },
    });
    const fx = TestBed.createComponent(MonthlyReportsComponent);
    fx.detectChanges();
    expect(fx.componentInstance.reports()).toBeNull();
  });
});
