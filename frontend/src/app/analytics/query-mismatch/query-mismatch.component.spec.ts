import { ComponentFixture, TestBed } from '@angular/core/testing';
import { QueryMismatchComponent } from './query-mismatch.component';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ChangeDetectorRef } from '@angular/core';

describe('QueryMismatchComponent', () => {
  let component: QueryMismatchComponent;
  let fixture: ComponentFixture<QueryMismatchComponent>;
  let httpMock: HttpTestingController;

  const mockRows = [
    {
      query: 'best internal linker',
      landing_page_id: 101,
      landing_page_title: 'About Us',
      clicks: 50,
      impressions: 1000,
      avg_position: 12.5
    }
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QueryMismatchComponent, HttpClientTestingModule, NoopAnimationsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(QueryMismatchComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create', () => {
    fixture.detectChanges();
    httpMock.expectOne('/api/analytics/query-mismatch/').flush([]);
    expect(component).toBeTruthy();
  });

  it('should load and render mismatch rows on init', () => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/analytics/query-mismatch/');
    req.flush(mockRows);
    
    const cdr = fixture.componentRef.injector.get(ChangeDetectorRef);
    cdr.detectChanges();

    expect(component.loading).toBe(false);
    expect(component.rows.length).toBe(1);

    const cards = fixture.nativeElement.querySelectorAll('.mismatch-card');
    expect(cards.length).toBe(1);
    expect(cards[0].textContent).toContain('best internal linker');
  });

  it('should show empty hint when no rows returned', () => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/analytics/query-mismatch/');
    req.flush([]);
    
    const cdr = fixture.componentRef.injector.get(ChangeDetectorRef);
    cdr.detectChanges();

    expect(component.loading).toBe(false);
    const emptyHint = fixture.nativeElement.querySelector('.empty-hint');
    expect(emptyHint).toBeTruthy();
  });

  it('should handle API error gracefully', () => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/analytics/query-mismatch/');
    req.error(new ErrorEvent('Network error'));
    
    const cdr = fixture.componentRef.injector.get(ChangeDetectorRef);
    cdr.detectChanges();

    expect(component.loading).toBe(false);
    expect(component.rows).toEqual([]);
  });
});
