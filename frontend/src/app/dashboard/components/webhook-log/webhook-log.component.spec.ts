import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of, NEVER } from 'rxjs';
import { WebhookLogComponent } from './webhook-log.component';
import { SyncService, WebhookReceipt } from '../../../jobs/sync.service';
import { RealtimeService } from '../../../core/services/realtime.service';

const MOCK_RECEIPTS: WebhookReceipt[] = [
  {
    receipt_id: 'r1',
    created_at: '2026-01-01T00:00:00Z',
    source: 'xenforo',
    event_type: 'post.created',
    status: 'ok',
    occurrence_count: 1,
    last_seen_at: '2026-01-01T00:00:00Z',
  },
  {
    receipt_id: 'r2',
    created_at: '2026-01-02T00:00:00Z',
    source: 'wordpress',
    event_type: 'post.updated',
    status: 'error',
    error_message: 'timeout',
    occurrence_count: 3,
    last_seen_at: '2026-01-02T00:00:00Z',
  },
];

describe('WebhookLogComponent', () => {
  let fixture: ComponentFixture<WebhookLogComponent>;
  let component: WebhookLogComponent;
  let syncSvcSpy: jasmine.SpyObj<SyncService>;

  /** A cold observable that never emits — simulates a connected but silent WebSocket. */
  const silentRealtime = { subscribeTopic: () => NEVER };

  beforeEach(async () => {
    syncSvcSpy = jasmine.createSpyObj('SyncService', ['getWebhookReceipts']);
    syncSvcSpy.getWebhookReceipts.and.returnValue(of(MOCK_RECEIPTS));

    await TestBed.configureTestingModule({
      imports: [WebhookLogComponent],
      providers: [
        provideNoopAnimations(),
        { provide: SyncService, useValue: syncSvcSpy },
        { provide: RealtimeService, useValue: silentRealtime },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(WebhookLogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders without error', () => {
    expect(fixture.nativeElement).toBeTruthy();
  });

  it('calls getWebhookReceipts on init', () => {
    expect(syncSvcSpy.getWebhookReceipts).toHaveBeenCalledTimes(1);
  });

  it('populates the receipts signal with the loaded data', () => {
    expect(component.receipts()).toEqual(MOCK_RECEIPTS);
  });

  it('renders one table row per receipt', () => {
    const rows = fixture.nativeElement.querySelectorAll('tr[mat-row]');
    expect(rows.length).toBe(MOCK_RECEIPTS.length);
  });

  it('shows an empty table when the service returns an empty array', () => {
    syncSvcSpy.getWebhookReceipts.and.returnValue(of([]));
    const f2 = TestBed.createComponent(WebhookLogComponent);
    f2.detectChanges();
    expect(f2.componentInstance.receipts().length).toBe(0);
  });

  it('shows the displayed columns for the table', () => {
    // Verifies the column definition list is non-empty and contains expected columns.
    const cols = fixture.componentInstance.displayedColumns;
    expect(cols).toContain('status');
    expect(cols).toContain('source');
    expect(cols.length).toBeGreaterThan(0);
  });
});
