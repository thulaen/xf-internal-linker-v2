import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PriorityActionQueueComponent } from './priority-action-queue.component';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

describe('PriorityActionQueueComponent', () => {
  let component: PriorityActionQueueComponent;
  let fixture: ComponentFixture<PriorityActionQueueComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PriorityActionQueueComponent],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(PriorityActionQueueComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render empty state when no actions', () => {
    component.actions = [];
    fixture.detectChanges();
    const emptyEl = fixture.debugElement.query(By.css('.paq-empty'));
    expect(emptyEl).toBeTruthy();
    expect(emptyEl.nativeElement.textContent).toContain('Nothing urgent');
  });

  it('should slice to top 3 actions and render list', () => {
    component.actions = [
      { title: 'Task 1', reason: 'A', severity: 'error', route: '/1', isBlocking: true },
      { title: 'Task 2', reason: 'B', severity: 'warning', route: '/2', isBlocking: false },
      { title: 'Task 3', reason: 'C', severity: 'info', route: '/3', isBlocking: false },
      { title: 'Task 4', reason: 'D', severity: 'info', route: '/4', isBlocking: false }
    ];
    fixture.detectChanges();

    expect(component.topActions.length).toBe(3);

    const items = fixture.debugElement.queryAll(By.css('.paq-item'));
    expect(items.length).toBe(3);

    expect(items[0].classes['severity-error']).toBe(true);
    expect(items[1].classes['severity-warning']).toBe(true);
    expect(items[2].classes['severity-info']).toBe(true);
  });

  it('should handle null actions gracefully', () => {
    component.actions = null;
    fixture.detectChanges();
    expect(component.topActions).toEqual([]);
    const emptyEl = fixture.debugElement.query(By.css('.paq-empty'));
    expect(emptyEl).toBeTruthy();
  });
});
