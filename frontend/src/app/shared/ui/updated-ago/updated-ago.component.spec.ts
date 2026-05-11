import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { UpdatedAgoComponent } from './updated-ago.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('UpdatedAgoComponent', () => {
  let component: UpdatedAgoComponent;
  let fixture: ComponentFixture<UpdatedAgoComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [UpdatedAgoComponent, NoopAnimationsModule]
    }).compileComponents();

    fixture = TestBed.createComponent(UpdatedAgoComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display "just now" for recent timestamps', () => {
    const now = new Date();
    component.updatedAt = now;
    fixture.detectChanges();
    
    const label = fixture.nativeElement.querySelector('.updated-ago-label');
    expect(label.textContent).toBe('just now');
  });

  it('should display "5m ago" after 5 minutes', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000);
    component.updatedAt = fiveMinAgo;
    fixture.detectChanges();

    const label = fixture.nativeElement.querySelector('.updated-ago-label');
    expect(label.textContent).toBe('5m ago');
  });

  it('should apply warn class after warnAfterMs', () => {
    const warnLimit = 5 * 60 * 1000;
    const pastLimit = new Date(Date.now() - warnLimit - 1000);
    component.updatedAt = pastLimit;
    component.warnAfterMs = warnLimit;
    fixture.detectChanges();

    const pill = fixture.nativeElement.querySelector('.updated-ago-pill');
    expect(pill.classList).toContain('updated-ago-warn');
  });

  it('should apply error class after errorAfterMs', () => {
    const errorLimit = 15 * 60 * 1000;
    const pastLimit = new Date(Date.now() - errorLimit - 1000);
    component.updatedAt = pastLimit;
    component.errorAfterMs = errorLimit;
    fixture.detectChanges();

    const pill = fixture.nativeElement.querySelector('.updated-ago-pill');
    expect(pill.classList).toContain('updated-ago-error');
  });

  it('should update label automatically on tick', fakeAsync(() => {
    const now = new Date();
    component.updatedAt = now;
    component.tickMs = 60000; // 1 min
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.updated-ago-label').textContent).toBe('just now');

    // Fast forward 1 minute
    tick(60000);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.updated-ago-label').textContent).toBe('1m ago');
    
    component.ngOnDestroy(); // Cleanup interval
  }));
});
