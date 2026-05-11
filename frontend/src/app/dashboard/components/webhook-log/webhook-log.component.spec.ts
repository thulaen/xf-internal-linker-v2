import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WebhookLogComponent } from './webhook-log.component';
import { SyncService } from '../../../jobs/sync.service';
import { RealtimeService } from '../../../core/services/realtime.service';
import { of, Subject } from 'rxjs';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { By } from '@angular/platform-browser';

describe('WebhookLogComponent', () => {
  let component: WebhookLogComponent;
  let fixture: ComponentFixture<WebhookLogComponent>;
  let syncSvcSpy: jasmine.SpyObj<SyncService>;
  let realtimeSvcSpy: jasmine.SpyObj<RealtimeService>;
  let receiptsSubject: Subject<any>;

  beforeEach(async () => {
    receiptsSubject = new Subject();
    syncSvcSpy = jasmine.createSpyObj('SyncService', ['getWebhookReceipts']);
    realtimeSvcSpy = jasmine.createSpyObj('RealtimeService', ['subscribeTopic']);

    syncSvcSpy.getWebhookReceipts.and.returnValue(of([]));
    realtimeSvcSpy.subscribeTopic.and.returnValue(receiptsSubject.asObservable());

    await TestBed.configureTestingModule({
      imports: [WebhookLogComponent, NoopAnimationsModule],
      providers: [
        { provide: SyncService, useValue: syncSvcSpy },
        { provide: RealtimeService, useValue: realtimeSvcSpy },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(WebhookLogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render empty state when no receipts', () => {
    component.receipts.set([]);
    fixture.detectChanges();
    const emptyState = fixture.debugElement.query(By.css('.empty-state'));
    expect(emptyState).toBeTruthy();
    expect(emptyState.nativeElement.textContent).toContain('No webhook activity');
  });

  it('should render table when receipts exist', () => {
    const mockReceipts = [
      {
        receipt_id: '1',
        created_at: new Date().toISOString(),
        source: 'xenforo',
        event_type: 'thread.create',
        status: 'processed',
        occurrence_count: 1
      }
    ];
    component.receipts.set(mockReceipts as any);
    fixture.detectChanges();
    
    const table = fixture.debugElement.query(By.css('.webhook-table'));
    expect(table).toBeTruthy();
    
    const rows = fixture.debugElement.queryAll(By.css('tr[mat-row]'));
    expect(rows.length).toBe(1);
    expect(rows[0].nativeElement.textContent).toContain('thread.create');
  });

  it('should update receipts on realtime create event', () => {
    const initialReceipts = [{ receipt_id: '1', event_type: 'old' }];
    component.receipts.set(initialReceipts as any);
    
    const newReceipt = {
      receipt_id: '2',
      event_type: 'new',
      source: 'wordpress',
      status: 'processed',
      created_at: new Date().toISOString(),
      occurrence_count: 1
    };
    
    receiptsSubject.next({
      event: 'receipt.created',
      payload: newReceipt
    });
    
    expect(component.receipts().length).toBe(2);
    expect(component.receipts()[0].receipt_id).toBe('2');
  });

  it('should remove receipt on realtime delete event', () => {
    const initialReceipts = [
      { receipt_id: '1', event_type: 'one' },
      { receipt_id: '2', event_type: 'two' }
    ];
    component.receipts.set(initialReceipts as any);
    
    receiptsSubject.next({
      event: 'receipt.deleted',
      payload: { receipt_id: '1' }
    });
    
    expect(component.receipts().length).toBe(1);
    expect(component.receipts()[0].receipt_id).toBe('2');
  });

  it('should show dedup count and tooltip when occurrence_count > 1', () => {
    const mockReceipts = [
      {
        receipt_id: '1',
        created_at: new Date().toISOString(),
        source: 'xenforo',
        event_type: 'ping',
        status: 'ignored',
        occurrence_count: 5
      }
    ];
    component.receipts.set(mockReceipts as any);
    fixture.detectChanges();
    
    const dedupCount = fixture.debugElement.query(By.css('.dedup-count'));
    expect(dedupCount).toBeTruthy();
    expect(dedupCount.nativeElement.textContent).toContain('×5');
  });

  it('should clean up interval on destroy', () => {
    const clearIntervalSpy = spyOn(window, 'clearInterval');
    // @ts-expect-error - accessing private for test
    component.refreshInterval = 123;
    component.ngOnDestroy();
    expect(clearIntervalSpy).toHaveBeenCalledWith(123);
  });
});
