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
  let brokenSvc: jasmine.SpyObj<BrokenLinkService>;

  beforeEach(async () => {
    brokenSvc = jasmine.createSpyObj<BrokenLinkService>('BrokenLinkService', [
      'list',
      'patch',
      'startScan',
      'exportCsv',
    ]);
    brokenSvc.list.and.returnValue(of(paginated([makeLink()])));
    brokenSvc.patch.and.returnValue(of(makeLink({ status: 'fixed' })));
    brokenSvc.startScan.and.returnValue(of({ job_id: 'scan1', message: 'started' }));

    await TestBed.configureTestingModule({
      imports: [LinkHealthComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: BrokenLinkService, useValue: brokenSvc },
        { provide: DashboardService, useValue: { updateOpenBrokenLinks: jasmine.createSpy('upd') } },
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
    expect(brokenSvc.list.calls.count()).toBeGreaterThanOrEqual(4);
    expect(component.brokenLinks().length).toBe(1);
  });

  it('setStatusFilter resets page to 1 and re-loads', () => {
    fixture.detectChanges();
    component.page.set(5);
    brokenSvc.list.calls.reset();
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
    brokenSvc.list.and.returnValue(throwError(() => new Error('500')));
    fixture.detectChanges();
    expect(component.loading()).toBeFalse();
  });
});
