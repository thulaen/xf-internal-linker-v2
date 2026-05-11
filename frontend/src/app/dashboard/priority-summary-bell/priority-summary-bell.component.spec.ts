import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PrioritySummaryBellComponent } from './priority-summary-bell.component';
import { By } from '@angular/platform-browser';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';

describe('PrioritySummaryBellComponent', () => {
  let component: PrioritySummaryBellComponent;
  let fixture: ComponentFixture<PrioritySummaryBellComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PrioritySummaryBellComponent, BrowserAnimationsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(PrioritySummaryBellComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should grade clear when no actions', () => {
    fixture.componentRef.setInput('actions', []);
    fixture.detectChanges();
    
    expect(component.grade()).toBe('clear');
    expect(component.totalCount()).toBe(0);
    expect(component.icon()).toBe('notifications_none');
    
    const button = fixture.debugElement.query(By.css('button'));
    expect(button.classes['psb-clear']).toBe(true);
  });

  it('should grade urgent when there are error or blocking actions', () => {
    fixture.componentRef.setInput('actions', [
      { title: 'T1', reason: 'R1', route: '/1', severity: 'error', isBlocking: false }
    ]);
    fixture.detectChanges();

    expect(component.grade()).toBe('urgent');
    expect(component.totalCount()).toBe(1);
    expect(component.icon()).toBe('notifications_active');
    
    const button = fixture.debugElement.query(By.css('button'));
    expect(button.classes['psb-urgent']).toBe(true);
  });

  it('should grade warning when there are non-error, non-blocking actions', () => {
    fixture.componentRef.setInput('actions', [
      { title: 'T1', reason: 'R1', route: '/1', severity: 'warning', isBlocking: false }
    ]);
    fixture.detectChanges();

    expect(component.grade()).toBe('warning');
    expect(component.totalCount()).toBe(1);
    expect(component.icon()).toBe('notifications');
    
    const button = fixture.debugElement.query(By.css('button'));
    expect(button.classes['psb-warning']).toBe(true);
  });
  
  it('should categorize actions into urgent and info', () => {
    fixture.componentRef.setInput('actions', [
      { title: 'T1', reason: 'R1', route: '/1', severity: 'error', isBlocking: false },
      { title: 'T2', reason: 'R2', route: '/2', severity: 'warning', isBlocking: true },
      { title: 'T3', reason: 'R3', route: '/3', severity: 'warning', isBlocking: false },
      { title: 'T4', reason: 'R4', route: '/4', severity: 'info', isBlocking: false }
    ]);
    fixture.detectChanges();

    expect(component.urgent().length).toBe(2);
    expect(component.info().length).toBe(2);
    expect(component.grade()).toBe('urgent');
  });

  it('should handle null/undefined inputs', () => {
    fixture.componentRef.setInput('actions', null);
    fixture.detectChanges();
    expect(component.totalCount()).toBe(0);
  });
});
