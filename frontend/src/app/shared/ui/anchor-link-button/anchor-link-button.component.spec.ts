import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { MatSnackBar } from '@angular/material/snack-bar';

import { AnchorLinkButtonComponent } from './anchor-link-button.component';

describe('AnchorLinkButtonComponent', () => {
  let component: AnchorLinkButtonComponent;
  let fixture: ComponentFixture<AnchorLinkButtonComponent>;
  let snackOpen: Spy;
  let clipboardSpy: Spy;

  beforeEach(async () => {
    clipboardSpy = vi.spyOn(navigator.clipboard, 'writeText').mockReturnValue(undefined as never);

    await TestBed.configureTestingModule({
      imports: [AnchorLinkButtonComponent],
      providers: [{ provide: MatSnackBar, useValue: createSpyObj(['open']) }],
    }).compileComponents();

    fixture = TestBed.createComponent(AnchorLinkButtonComponent);
    component = fixture.componentInstance;
    snackOpen = vi.spyOn((component as unknown as { snack: MatSnackBar }).snack, 'open');
    fixture.componentRef.setInput('anchorId', 'throughput');
    fixture.detectChanges();
  });

  it('renders a copy-link button', () => {
    const button = fixture.debugElement.query(By.css('button'));
    const icon = fixture.debugElement.query(By.css('mat-icon'));

    expect(button.nativeElement.getAttribute('aria-label')).toBe('Copy link to this section');
    expect(icon.nativeElement.textContent.trim()).toBe('link');
  });

  it('copies the current page link with the anchor id', async () => {
    clipboardSpy.mockReturnValue(Promise.resolve());

    await component.copyLink();

    expect(clipboardSpy).toHaveBeenCalledWith(
      `${window.location.origin}${window.location.pathname}#throughput`,
    );
    expect(snackOpen).toHaveBeenCalledWith(expect.stringMatching(/^Link copied/), 'OK', {
      duration: 2500,
    });
  });

  it('does nothing when the anchor id is missing', async () => {
    fixture.componentRef.setInput('anchorId', '');
    fixture.detectChanges();

    await component.copyLink();

    expect(clipboardSpy).not.toHaveBeenCalled();
    expect(snackOpen).not.toHaveBeenCalled();
  });

  it('shows a plain fallback message when copying fails', async () => {
    clipboardSpy.mockReturnValue(Promise.reject(new Error('blocked')));

    await component.copyLink();

    expect(snackOpen).toHaveBeenCalledWith(
      'Could not copy — long-press your browser address bar and share manually.',
      'OK',
      { duration: 4000 },
    );
  });
});
