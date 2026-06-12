import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AuditTrailComponent } from './audit-trail.component';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { Pipe, PipeTransform } from '@angular/core';
import { By } from '@angular/platform-browser';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

@Pipe({ name: 'timeAgo', standalone: true })
class MockTimeAgoPipe implements PipeTransform {
  transform(_value: string): string { return '2 hours ago'; }
}

@Pipe({ name: 'intlDateTime', standalone: true })
class MockIntlDateTimePipe implements PipeTransform {
  transform(_value: string): string { return 'Jan 1, 2026, 10:00 AM'; }
}

describe('AuditTrailComponent', () => {
  let component: AuditTrailComponent;
  let fixture: ComponentFixture<AuditTrailComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        AuditTrailComponent,
        HttpClientTestingModule,
        MockTimeAgoPipe,
        MockIntlDateTimePipe,
        MatIconModule,
        MatProgressSpinnerModule
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(AuditTrailComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should fetch and display audit entries', () => {
    fixture.componentRef.setInput('targetType', 'suggestion');
    fixture.componentRef.setInput('targetId', '123');
    fixture.detectChanges();

    const mockEntries = [
      { id: 1, action: 'Created', target_type: 'suggestion', target_id: '123', created_at: '2026-05-10T10:00:00Z', actor: 'admin' },
      { id: 2, action: 'Approved', target_type: 'suggestion', target_id: '123', created_at: '2026-05-10T12:00:00Z', actor: 'editor' }
    ];

    const req = httpMock.expectOne(req => req.url === '/api/audit-entries/' && req.params.get('target_id') === '123');
    expect(req.request.method).toBe('GET');
    req.flush(mockEntries);
    fixture.detectChanges();

    expect(component.loading()).toBe(false);
    expect(component.entries().length).toBe(2);
    
    const items = fixture.debugElement.queryAll(By.css('.at-item'));
    expect(items.length).toBe(2);
    
    // First item in list should be the newest one (id 2) because it sorts desc
    expect(items[0].query(By.css('.at-action')).nativeElement.textContent).toBe('Approved');
    expect(items[0].query(By.css('.at-actor')).nativeElement.textContent).toContain('editor');
  });

  it('should show empty state when no entries found', () => {
    fixture.componentRef.setInput('targetType', 'suggestion');
    fixture.componentRef.setInput('targetId', '123');
    fixture.detectChanges();

    const req = httpMock.expectOne(req => req.url === '/api/audit-entries/');
    req.flush([]);
    fixture.detectChanges();

    expect(fixture.debugElement.query(By.css('.at-empty'))).toBeTruthy();
    expect(fixture.debugElement.query(By.css('.at-empty')).nativeElement.textContent).toContain('No audit history yet for this suggestion');
  });

  it('should handle error during fetch', () => {
    fixture.componentRef.setInput('targetType', 'suggestion');
    fixture.componentRef.setInput('targetId', '123');
    fixture.detectChanges();

    const req = httpMock.expectOne(req => req.url === '/api/audit-entries/');
    req.error(new ErrorEvent('Network error'));
    fixture.detectChanges();

    expect(component.loading()).toBe(false);
    expect(component.entries().length).toBe(0);
    expect(fixture.debugElement.query(By.css('.at-empty'))).toBeTruthy();
  });
});
