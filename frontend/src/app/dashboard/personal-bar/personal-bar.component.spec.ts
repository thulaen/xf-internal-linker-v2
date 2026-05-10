import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { PersonalBarComponent } from './personal-bar.component';
import { AuthService } from '../../core/services/auth.service';

describe('PersonalBarComponent', () => {
  let component: PersonalBarComponent;
  let fixture: ComponentFixture<PersonalBarComponent>;
  let mockAuth: Partial<AuthService>;

  beforeEach(async () => {
    localStorage.clear();
    mockAuth = {
      currentUser$: of({ username: 'Alice' })
    };

    await TestBed.configureTestingModule({
      imports: [PersonalBarComponent],
      providers: [
        { provide: AuthService, useValue: mockAuth }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(PersonalBarComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display the username', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.pb-greet-line')?.textContent).toContain('Alice');
  });

  it('should show correct greeting based on time', () => {
    const morning = new Date();
    morning.setHours(9);
    component.now.set(morning);
    fixture.detectChanges();
    expect(component.greeting()).toBe('Good morning');

    const evening = new Date();
    evening.setHours(19);
    component.now.set(evening);
    fixture.detectChanges();
    expect(component.greeting()).toBe('Good evening');
  });

  it('should handle streak increment', () => {
    // Mock yesterday's visit
    const d = new Date();
    d.setDate(d.getDate() - 1);
    const yesterday = `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`;
    localStorage.setItem('xfil_visit_streak', '5');
    localStorage.setItem('xfil_visit_streak_last_day', yesterday);
    
    // Re-init to trigger bump
    component.ngOnInit();
    fixture.detectChanges();
    
    expect(component.streak()).toBe(6);
    expect(localStorage.getItem('xfil_visit_streak')).toBe('6');
  });

  it('should show last visit label', () => {
    const threeHoursAgo = Date.now() - (3 * 60 * 60 * 1000);
    localStorage.setItem('xfil_last_visit_detail', JSON.stringify({ ts: threeHoursAgo }));
    
    component.ngOnInit();
    fixture.detectChanges();
    
    expect(component.lastVisitLabel()).toContain('last seen 3h ago');
  });
});
