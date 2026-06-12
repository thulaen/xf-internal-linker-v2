import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RotatingCardComponent } from './rotating-card.component';
import { ContentSnippet } from './content-cards.data';

describe('RotatingCardComponent', () => {
  let component: RotatingCardComponent;
  let fixture: ComponentFixture<RotatingCardComponent>;

  const mockBank: ContentSnippet[] = [
    { id: '1', text: 'Win 1', attribution: 'User A' },
    { id: '2', text: 'Win 2', attribution: 'User B' },
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RotatingCardComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(RotatingCardComponent);
    component = fixture.componentInstance;
    component.title = 'Wins';
    component.icon = 'star';
    component.bank = mockBank;
    component.storageKey = 'test_wins';
  });

  it('should create', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should render the title and icon', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('mat-card-title')?.textContent).toBe('Wins');
    expect(compiled.querySelector('mat-icon[mat-card-avatar]')?.textContent).toBe('star');
  });

  it('should render a snippet from the bank', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.querySelector('.rc-text')?.textContent;
    expect(mockBank.some(s => s.text === text)).toBe(true);
  });

  it('should rotate to another snippet on next()', () => {
    fixture.detectChanges();
    const firstId = component.current()?.id;
    component.next();
    fixture.detectChanges();
    const secondId = component.current()?.id;
    // With only 2 snippets, it MUST change.
    expect(secondId).not.toBe(firstId);
  });

  it('should hide controls when showControls is false', () => {
    component.showControls = false;
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('mat-card-actions')).toBeNull();
  });

  it('should apply accent classes', () => {
    component.accent = 'good';
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.rc-card')?.classList).toContain('rc-accent-good');
  });
});
