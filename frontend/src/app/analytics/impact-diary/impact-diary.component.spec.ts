import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ImpactDiaryComponent } from './impact-diary.component';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ChangeDetectorRef } from '@angular/core';

describe('ImpactDiaryComponent', () => {
  let component: ImpactDiaryComponent;
  let fixture: ComponentFixture<ImpactDiaryComponent>;
  let httpMock: HttpTestingController;

  const mockEntries = [
    {
      suggestion_id: 's1',
      metric_type: 'Clicks',
      before_value: 100,
      after_value: 120,
      delta_percent: 20.0,
      attribution_model: 'Direct',
      confidence: 'high',
      is_conclusive: true,
      control_match_count: 50,
      created_at: '2026-05-10T10:00:00Z'
    }
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ImpactDiaryComponent, HttpClientTestingModule, NoopAnimationsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(ImpactDiaryComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create', () => {
    fixture.detectChanges();
    httpMock.expectOne('/api/analytics/impacts/').flush([]);
    expect(component).toBeTruthy();
  });

  it('should load and render entries on init', () => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/analytics/impacts/');
    req.flush(mockEntries);
    
    const cdr = fixture.componentRef.injector.get(ChangeDetectorRef);
    cdr.detectChanges();

    expect(component.loading).toBe(false);
    expect(component.entries.length).toBe(1);

    const cards = fixture.nativeElement.querySelectorAll('.timeline-card');
    expect(cards.length).toBe(1);
    expect(cards[0].textContent).toContain('Clicks');
    expect(cards[0].textContent).toContain('+20.0%');
  });

  it('should show empty hint when no entries returned', () => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/analytics/impacts/');
    req.flush([]);
    
    const cdr = fixture.componentRef.injector.get(ChangeDetectorRef);
    cdr.detectChanges();

    expect(component.loading).toBe(false);
    const emptyHint = fixture.nativeElement.querySelector('.empty-hint');
    expect(emptyHint).toBeTruthy();
  });

  it('should handle API error gracefully', () => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/analytics/impacts/');
    req.error(new ErrorEvent('Network error'));
    
    const cdr = fixture.componentRef.injector.get(ChangeDetectorRef);
    cdr.detectChanges();

    expect(component.loading).toBe(false);
    expect(component.entries).toEqual([]);
  });
});
