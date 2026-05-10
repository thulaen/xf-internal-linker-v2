import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { OperatorChecklistComponent } from './operator-checklist.component';

describe('OperatorChecklistComponent', () => {
  let component: OperatorChecklistComponent;
  let fixture: ComponentFixture<OperatorChecklistComponent>;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [OperatorChecklistComponent],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(OperatorChecklistComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should start with 0 checked items', () => {
    expect(component.checkedCount()).toBe(0);
    expect(component.progressPercent()).toBe(0);
  });

  it('should update count and progress when an item is toggled', () => {
    component.toggle('alerts', true);
    fixture.detectChanges();
    expect(component.checkedCount()).toBe(1);
    expect(component.progressPercent()).toBeGreaterThan(0);
    expect(localStorage.getItem('xfil_operator_checklist')).toContain('alerts');
  });

  it('should show celebration message when all items are checked', () => {
    component.items.forEach(item => component.toggle(item.id, true));
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.oc-done')).toBeTruthy();
    expect(component.progressPercent()).toBe(100);
  });

  it('should purge stale data from yesterday', () => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const yKey = yesterday.toISOString().split('T')[0];
    localStorage.setItem('xfil_operator_checklist', JSON.stringify({ date: yKey, checks: { alerts: true } }));
    
    // Re-initialize component to trigger readToday
    component.ngOnInit();
    expect(component.checkedCount()).toBe(0);
    // Should have purged
    expect(localStorage.getItem('xfil_operator_checklist')).toBeNull();
  });
});
