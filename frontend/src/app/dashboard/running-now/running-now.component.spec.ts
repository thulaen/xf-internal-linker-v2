import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RunningNowComponent, RunningTask } from './running-now.component';
import { provideRouter } from '@angular/router';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('RunningNowComponent', () => {
  let component: RunningNowComponent;
  let fixture: ComponentFixture<RunningNowComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RunningNowComponent, NoopAnimationsModule],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(RunningNowComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show empty state when no tasks are running', () => {
    component.activeTasks = [];
    fixture.detectChanges();
    const emptyState = fixture.nativeElement.querySelector('app-empty-state');
    expect(emptyState).toBeTruthy();
    expect(emptyState.getAttribute('heading')).toBe('No tasks running');
  });

  it('should show tasks when activeTasks is populated', () => {
    const mockTasks: RunningTask[] = [
      { name: 'Syncing', progress: 50, message: 'Processing...', eta_seconds: 120, state: 'RUNNING' }
    ];
    fixture.componentRef.setInput('activeTasks', mockTasks);
    fixture.detectChanges();
    
    const taskRows = fixture.nativeElement.querySelectorAll('.task-row');
    expect(taskRows.length).toBe(1);
    expect(taskRows[0].querySelector('.task-name').textContent).toContain('Syncing');
    expect(taskRows[0].querySelector('.task-eta').textContent).toContain('2m');
  });

  it('should format ETA correctly', () => {
    expect(component.formatEta(45)).toBe('45s');
    expect(component.formatEta(120)).toBe('2m');
    expect(component.formatEta(3660)).toBe('1h 1m');
  });
});
