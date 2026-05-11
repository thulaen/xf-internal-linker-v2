import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TrendDeltasComponent } from './trend-deltas.component';
import { DashboardData } from '../dashboard.service';

describe('TrendDeltasComponent', () => {
  let component: TrendDeltasComponent;
  let fixture: ComponentFixture<TrendDeltasComponent>;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [TrendDeltasComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(TrendDeltasComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should handle null data gracefully', () => {
    fixture.componentRef.setInput('data', null);
    fixture.detectChanges();
    expect(component.tiles()).toEqual([]);
  });

  it('should calculate tiles with data and no localStorage (baseline)', () => {
    const mockData = {
      suggestion_counts: { pending: 10, approved: 5, applied: 2 },
      content_count: 100
    } as DashboardData;

    fixture.componentRef.setInput('data', mockData);
    fixture.componentRef.setInput('openBrokenLinks', 3);
    fixture.detectChanges();

    const tiles = component.tiles();
    expect(tiles.length).toBe(5);
    
    // Everything should be compared against 0 since no yesterday data exists
    expect(tiles.find(t => t.key === 'pending_reviews')?.value).toBe(10);
    expect(tiles.find(t => t.key === 'pending_reviews')?.yesterday).toBe(0);
    
    expect(tiles.find(t => t.key === 'broken_links')?.value).toBe(3);
  });

  it('should verify verdicts correctly', () => {
    const mockData = {
      suggestion_counts: { pending: 10, approved: 5, applied: 2 },
      content_count: 100
    } as DashboardData;

    fixture.componentRef.setInput('data', mockData);
    fixture.detectChanges();
    
    const tile1 = { key: 't1', label: 'T1', value: 10, yesterday: 5 };
    const tile2 = { key: 't2', label: 'T2', value: 5, yesterday: 10 };
    const tile3 = { key: 't3', label: 'T3', value: 5, yesterday: 5 };
    const tileInv = { key: 't4', label: 'T4', value: 10, yesterday: 5, inverted: true };
    const tileInv2 = { key: 't5', label: 'T5', value: 5, yesterday: 10, inverted: true };

    expect(component.verdictFor(tile1)).toBe('good');
    expect(component.verdictFor(tile2)).toBe('bad');
    expect(component.verdictFor(tile3)).toBe('flat');
    expect(component.verdictFor(tileInv)).toBe('bad');
    expect(component.verdictFor(tileInv2)).toBe('good');
  });
  
  it('should determine correct arrow and delta label', () => {
    const tile1 = { key: 't1', label: 'T1', value: 10, yesterday: 5 };
    expect(component.arrowFor(tile1)).toBe('arrow_upward');
    expect(component.deltaLabel(tile1)).toBe('+5');
    
    const tile2 = { key: 't2', label: 'T2', value: 5, yesterday: 10 };
    expect(component.arrowFor(tile2)).toBe('arrow_downward');
    expect(component.deltaLabel(tile2)).toBe('-5');
    
    const tile3 = { key: 't3', label: 'T3', value: 5, yesterday: 5 };
    expect(component.arrowFor(tile3)).toBe('remove');
    expect(component.deltaLabel(tile3)).toBe('unchanged');
  });

  it('should read from yesterday localStorage correctly', () => {
    // Setup yesterday in local storage
    const d = new Date();
    d.setDate(d.getDate() - 1);
    const y = d.getFullYear();
    const m = (d.getMonth() + 1).toString().padStart(2, '0');
    const day = d.getDate().toString().padStart(2, '0');
    const ystrKey = `${y}-${m}-${day}`;
    
    localStorage.setItem('xfil_dashboard_yesterday', JSON.stringify({
      [ystrKey]: {
        pending_reviews: 12,
        approved: 4,
        applied: 1,
        broken_links: 5,
        content: 95
      }
    }));
    
    // Re-create component so it reads localStorage
    fixture = TestBed.createComponent(TrendDeltasComponent);
    component = fixture.componentInstance;
    
    const mockData = {
      suggestion_counts: { pending: 10, approved: 5, applied: 2 },
      content_count: 100
    } as DashboardData;

    fixture.componentRef.setInput('data', mockData);
    fixture.componentRef.setInput('openBrokenLinks', 3);
    fixture.detectChanges();
    
    const tiles = component.tiles();
    expect(tiles.find(t => t.key === 'pending_reviews')?.yesterday).toBe(12);
    expect(tiles.find(t => t.key === 'approved')?.yesterday).toBe(4);
    expect(tiles.find(t => t.key === 'broken_links')?.yesterday).toBe(5);
  });
});
