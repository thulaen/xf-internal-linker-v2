import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WeeklyDigestOptinComponent } from './weekly-digest-optin.component';
import { By } from '@angular/platform-browser';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';

describe('WeeklyDigestOptinComponent', () => {
  let component: WeeklyDigestOptinComponent;
  let fixture: ComponentFixture<WeeklyDigestOptinComponent>;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [
        WeeklyDigestOptinComponent,
        MatSnackBarModule,
        BrowserAnimationsModule
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(WeeklyDigestOptinComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('should create with defaults', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
    expect(component.prefs().enabled).toBe(false);
    expect(component.prefs().day).toBe('monday');
    expect(component.prefs().time).toBe('08:00');
  });

  it('should toggle enabled state and save to local storage', () => {
    fixture.detectChanges();
    
    // Initial state
    let toggle = fixture.debugElement.query(By.css('mat-slide-toggle'));
    expect(toggle.nativeElement.textContent).toContain('Digest is OFF');
    
    // Call setEnabled directly as the UI might require complex interaction to trigger
    component.setEnabled(true);
    fixture.detectChanges();
    
    expect(component.prefs().enabled).toBe(true);
    toggle = fixture.debugElement.query(By.css('mat-slide-toggle'));
    expect(toggle.nativeElement.textContent).toContain('Digest is ON');
    
    // Verify localStorage
    const saved = JSON.parse(localStorage.getItem('xfil_weekly_digest') || '{}');
    expect(saved.enabled).toBe(true);
  });

  it('should update day and time preferences', () => {
    fixture.detectChanges();
    
    component.setEnabled(true);
    fixture.detectChanges();
    
    component.setDay('friday');
    component.setTime('18:00');
    
    expect(component.prefs().day).toBe('friday');
    expect(component.prefs().time).toBe('18:00');
    
    const saved = JSON.parse(localStorage.getItem('xfil_weekly_digest') || '{}');
    expect(saved.day).toBe('friday');
    expect(saved.time).toBe('18:00');
  });

  it('should load preferences from local storage on init', () => {
    localStorage.setItem('xfil_weekly_digest', JSON.stringify({
      enabled: true,
      day: 'wednesday',
      time: '12:00'
    }));
    
    // Recreate to trigger ngOnInit with data in localStorage
    fixture = TestBed.createComponent(WeeklyDigestOptinComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
    
    expect(component.prefs().enabled).toBe(true);
    expect(component.prefs().day).toBe('wednesday');
    expect(component.prefs().time).toBe('12:00');
  });
});
