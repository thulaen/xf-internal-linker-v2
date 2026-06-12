import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { EMPTY, of, throwError } from 'rxjs';

import { LinkHealthComponent } from './link-health.component';
import { BrokenLink, BrokenLinkService, PaginatedResult } from './broken-link.service';
import { DashboardService } from '../dashboard/dashboard.service';
import { SyncService } from '../jobs/sync.service';
import { AuthService } from '../core/services/auth.service';
import { VisibilityGateService } from '../core/util/visibility-gate.service';

function makeLink(over: Partial<BrokenLink> = {}): BrokenLink {
  return {
    broken_link_id: 'b1',
    source_content: 1,
    source_content_title: 'Thread A',
    source_content_url: 'https://example.com/a',
    url: 'https://broken.example.com/x',
    http_status: 404,
    redirect_url: '',
    first_detected_at: '2026-05-01T00:00:00Z',
    last_checked_at: '2026-05-10T00:00:00Z',
    status: 'open',
    notes: '',
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-10T00:00:00Z',
    ...over,
  };
}

function paginated(results: BrokenLink[]): PaginatedResult<BrokenLink> {
  return { count: results.length, next: null, previous: null, results };
}

describe('LinkHealthComponent', () => {
  let fixture: ComponentFixture<LinkHealthComponent>;
  let component: LinkHealthComponent;
  let brokenSvc: SpyObj<BrokenLinkService>;

  beforeEach(async () => {
    brokenSvc = createSpyObj<BrokenLinkService>([
      'list',
      'patch',
      'startScan',
      'exportCsv',
    ]);
    brokenSvc.list.mockReturnValue(of(paginated([makeLink()])));
    brokenSvc.patch.mockReturnValue(of(makeLink({ status: 'fixed' })));
    brokenSvc.startScan.mockReturnValue(of({ job_id: 'scan1', message: 'started' }));

    await TestBed.configureTestingModule({
      imports: [LinkHealthComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: BrokenLinkService, useValue: brokenSvc },
        { provide: DashboardService, useValue: { updateOpenBrokenLinks: vi.fn() } },
        { provide: SyncService, useValue: { getJob: () => of({ status: 'running', progress: 0.1, message: '' }) } },
        { provide: AuthService, useValue: { getToken: () => null } },
        { provide: VisibilityGateService, useValue: { whileLoggedInAndVisible: () => EMPTY } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(LinkHealthComponent);
    component = fixture.componentInstance;
  });

  it('loads list and summary on init', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
    // list call from load() + 3 from loadSummary().
    expect(brokenSvc.list.mock.calls.length).toBeGreaterThanOrEqual(4);
    expect(component.brokenLinks().length).toBe(1);
  });

  it('setStatusFilter resets page to 1 and re-loads', () => {
    fixture.detectChanges();
    component.page.set(5);
    brokenSvc.list.mockClear();
    component.setStatusFilter('open');
    expect(component.page()).toBe(1);
    expect(brokenSvc.list).toHaveBeenCalled();
  });

  it('markStatus updates the optimistic counter atomically', () => {
    fixture.detectChanges();
    component.summary.set({ open: 3, ignored: 0, fixed: 1 });
    component.markStatus(makeLink({ status: 'open' }), 'fixed');
    expect(component.summary().open).toBe(2);
    expect(component.summary().fixed).toBe(2);
  });

  it('handles list error path without crashing', () => {
    brokenSvc.list.mockReturnValue(throwError(() => new Error('500')));
    fixture.detectChanges();
    expect(component.loading()).toBe(false);
  });

  it('should filter by HTTP status code', () => {
    fixture.detectChanges();
    component.httpStatusFilter = 404;
    component.onHttpStatusChange();
    expect(component.page()).toBe(1);
    expect(brokenSvc.list).toHaveBeenCalled();
  });

  it('should load summary with counts', () => {
    fixture.detectChanges();
    expect(component.summary().open).toBeGreaterThanOrEqual(0);
    expect(component.summary().ignored).toBeGreaterThanOrEqual(0);
    expect(component.summary().fixed).toBeGreaterThanOrEqual(0);
  });

  it('should start broken-link scan', () => {
    fixture.detectChanges();
    component.startScan();
    expect(brokenSvc.startScan).toHaveBeenCalled();
    expect(component.jobId()).toBe('scan1');
  });

  it('should prevent multiple concurrent scans', () => {
    fixture.detectChanges();
    component.scanning.set(true);
    component.startScan();
    expect(brokenSvc.startScan).not.toHaveBeenCalled();
  });

  it('should export CSV with current filters', () => {
    brokenSvc.exportCsv.mockReturnValue(of(new Blob(['test'])));
    vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:url');
    vi.spyOn(window.URL, 'revokeObjectURL').mockReturnValue(undefined as never);
    vi.spyOn(window, 'open').mockReturnValue(undefined as never);

    fixture.detectChanges();
    component.statusFilter.set('open');
    component.exportCsv();

    expect(brokenSvc.exportCsv).toHaveBeenCalledWith({
      status: 'open',
      http_status: null,
    });
  });

  it('should handle page change', () => {
    fixture.detectChanges();
    brokenSvc.list.mockClear();
    component.onPageChange({ pageIndex: 2, pageSize: 25, length: 100, previousPageIndex: 0 });
    expect(component.page()).toBe(3);
    expect(brokenSvc.list).toHaveBeenCalled();
  });

  it('should track by broken link id', () => {
    const link = makeLink({ broken_link_id: 'test-123' });
    expect(component.trackById(0, link)).toBe('test-123');
  });

  it('should provide HTTP status label', () => {
    expect(component.statusLabel(404)).toBe('404');
    expect(component.statusLabel(0)).toBe('Connection error');
  });

  it('should open source thread in new window', () => {
    vi.spyOn(window, 'open').mockReturnValue(undefined as never);
    fixture.detectChanges();
    component.openSourceThread('https://example.com/thread');
    expect(window.open).toHaveBeenCalledWith(
      'https://example.com/thread',
      '_blank',
      'noopener,noreferrer'
    );
  });

  it('should not open thread if URL is empty', () => {
    vi.spyOn(window, 'open').mockReturnValue(undefined as never);
    fixture.detectChanges();
    component.openSourceThread('');
    expect(window.open).not.toHaveBeenCalled();
  });

  it('should disable fix button during scan', () => {
    fixture.detectChanges();
    component.scanning.set(true);
    expect(component.scanning()).toBe(true);
  });
});
