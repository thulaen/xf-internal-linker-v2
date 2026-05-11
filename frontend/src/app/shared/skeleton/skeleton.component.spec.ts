import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SkeletonComponent } from './skeleton.component';
import { By } from '@angular/platform-browser';

describe('SkeletonComponent', () => {
  let fixture: ComponentFixture<SkeletonComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SkeletonComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(SkeletonComponent);
    fixture.detectChanges();
  });

  it('should render card shape by default', () => {
    const card = fixture.debugElement.query(By.css('.skeleton-card'));
    expect(card).toBeTruthy();
    expect(card.nativeElement.getAttribute('aria-busy')).toBe('true');
    expect(fixture.debugElement.queryAll(By.css('.skeleton-line')).length).toBe(4);
  });

  it('should render table shape with specified rows', () => {
    fixture.componentRef.setInput('shape', 'table');
    fixture.componentRef.setInput('rows', 5);
    fixture.detectChanges();
    
    const table = fixture.debugElement.query(By.css('.skeleton-table'));
    expect(table).toBeTruthy();
    
    const rows = fixture.debugElement.queryAll(By.css('.skeleton-row'));
    expect(rows.length).toBe(5);
    
    // Each row should have 5 cells
    const cells = rows[0].queryAll(By.css('.skeleton-cell'));
    expect(cells.length).toBe(5);
  });

  it('should render block shape with specified height', () => {
    fixture.componentRef.setInput('shape', 'block');
    fixture.componentRef.setInput('height', 200);
    fixture.detectChanges();
    
    const block = fixture.debugElement.query(By.css('.skeleton-block'));
    expect(block).toBeTruthy();
    expect(block.nativeElement.style.height).toBe('200px');
  });

  it('should have accessibility labels', () => {
    const status = fixture.debugElement.query(By.css('[role="status"]'));
    expect(status.nativeElement.getAttribute('aria-label')).toBe('Loading content');
    
    const hidden = fixture.debugElement.query(By.css('.visually-hidden'));
    expect(hidden.nativeElement.textContent).toBe('Loading…');
  });
});
