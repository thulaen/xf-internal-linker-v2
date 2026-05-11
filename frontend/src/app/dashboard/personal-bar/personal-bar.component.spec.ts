import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PersonalBarComponent } from './personal-bar.component';
import { AuthService } from '../../core/services/auth.service';
import { of } from 'rxjs';
import { DatePipe } from '@angular/common';

describe('PersonalBarComponent', () => {
  let component: PersonalBarComponent;
  let fixture: ComponentFixture<PersonalBarComponent>;
  let mockAuth: jasmine.SpyObj<AuthService>;

  beforeEach(async () => {
    mockAuth = jasmine.createSpyObj('AuthService', [], {
      currentUser$: of({ username: 'Alice' })
    });

    await TestBed.configureTestingModule({
      imports: [PersonalBarComponent],
      providers: [
        { provide: AuthService, useValue: mockAuth },
        DatePipe
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(PersonalBarComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should display the username from AuthService', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.pb-greet-line')?.textContent).toContain('Alice');
  });

  it('should show "Good morning" before 12:00', () => {
    const morningDate = new Date();
    morningDate.setHours(9);
    component.now.set(morningDate);
    fixture.detectChanges();
    expect(component.greeting()).toBe('Good morning');
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.pb-greet-line')?.textContent).toContain('Good morning');
  });

  it('should show "Good afternoon" between 12:00 and 17:00', () => {
    const afternoonDate = new Date();
    afternoonDate.setHours(14);
    component.now.set(afternoonDate);
    fixture.detectChanges();
    expect(component.greeting()).toBe('Good afternoon');
  });

  it('should show "Good evening" between 17:00 and 21:00', () => {
    const eveningDate = new Date();
    eveningDate.setHours(19);
    component.now.set(eveningDate);
    fixture.detectChanges();
    expect(component.greeting()).toBe('Good evening');
  });

  it('should show "Working late" after 21:00', () => {
    const lateDate = new Date();
    lateDate.setHours(23);
    component.now.set(lateDate);
    fixture.detectChanges();
    expect(component.greeting()).toBe('Working late');
  });

  it('should render the current time in HH:mm format', () => {
    const testDate = new Date(2026, 4, 11, 15, 45); // 15:45
    component.now.set(testDate);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.pb-time')?.textContent?.trim()).toBe('15:45');
  });
});
