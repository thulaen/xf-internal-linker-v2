import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TopOpportunityPagesComponent } from './top-opportunity-pages.component';
import { By } from '@angular/platform-browser';

describe('TopOpportunityPagesComponent', () => {
  let component: TopOpportunityPagesComponent;
  let fixture: ComponentFixture<TopOpportunityPagesComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TopOpportunityPagesComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(TopOpportunityPagesComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display empty state when no pages are provided', () => {
    component.pages = [];
    fixture.detectChanges();
    const emptyState = fixture.debugElement.query(By.css('app-empty-state'));
    expect(emptyState).toBeTruthy();
  });

  it('should display table when pages are provided', () => {
    component.pages = [
      { title: 'Page A', url: 'http://a.com', opportunity_score: 95.5 },
      { title: 'Page B', url: 'http://b.com', opportunity_score: 80.1 }
    ];
    fixture.detectChanges();
    
    const emptyState = fixture.debugElement.query(By.css('app-empty-state'));
    expect(emptyState).toBeFalsy();
    
    const table = fixture.debugElement.query(By.css('table'));
    expect(table).toBeTruthy();
    
    const rows = fixture.debugElement.queryAll(By.css('tr[mat-row]'));
    expect(rows.length).toBe(2);
    
    const titleCell = rows[0].query(By.css('.page-link'));
    expect(titleCell.nativeElement.textContent).toContain('Page A');
    
    const scoreCell = rows[0].query(By.css('.score-value'));
    // Decimal pipe format '1.0-1' formats 95.5 to 95.5
    expect(scoreCell.nativeElement.textContent).toContain('95.5');
  });
});
