import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TodayFocusComponent } from './today-focus.component';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

describe('TodayFocusComponent', () => {
  let component: TodayFocusComponent;
  let fixture: ComponentFixture<TodayFocusComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TodayFocusComponent],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(TodayFocusComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render empty state when no actions are provided', () => {
    component.actions = [];
    fixture.detectChanges();
    const emptyState = fixture.debugElement.query(By.css('app-empty-state'));
    expect(emptyState).toBeTruthy();
  });

  it('should render actions in a list', () => {
    component.actions = [
      { title: 'Action 1', reason: 'R1', route: '/r1', severity: 'info', isBlocking: false },
      { title: 'Action 2', reason: 'R2', route: '/r2', severity: 'error', isBlocking: true },
      { title: 'Action 3', reason: 'R3', route: '/r3', severity: 'warning', isBlocking: false }
    ];
    fixture.detectChanges();

    const rows = fixture.debugElement.queryAll(By.css('.action-row'));
    expect(rows.length).toBe(3);

    expect(rows[0].classes['severity-info']).toBe(true);
    expect(rows[1].classes['severity-error']).toBe(true);
    expect(rows[2].classes['severity-warning']).toBe(true);

    const titleEl = rows[0].query(By.css('.action-title'));
    expect(titleEl.nativeElement.textContent).toContain('Action 1');
  });

  it('should map severity to icon correctly', () => {
    expect(component.severityIcon('error')).toBe('error');
    expect(component.severityIcon('warning')).toBe('warning');
    expect(component.severityIcon('info')).toBe('info');
    expect(component.severityIcon('unknown')).toBe('info');
  });
});
