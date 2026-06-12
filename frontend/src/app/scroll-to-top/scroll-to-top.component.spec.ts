import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { ScrollToTopComponent } from './scroll-to-top.component';
import { By } from '@angular/platform-browser';

describe('ScrollToTopComponent', () => {
  let component: ScrollToTopComponent;
  let fixture: ComponentFixture<ScrollToTopComponent>;
  let scrollContainer: HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ScrollToTopComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(ScrollToTopComponent);
    component = fixture.componentInstance;
    
    scrollContainer = document.createElement('div');
    scrollContainer.style.height = '100px';
    scrollContainer.style.overflow = 'scroll';
    scrollContainer.className = 'test-scroll-container';
    const content = document.createElement('div');
    content.style.height = '1000px';
    scrollContainer.appendChild(content);
    document.body.appendChild(scrollContainer);

    component.scrollTarget = scrollContainer;
  });

  afterEach(() => {
    if (document.body.contains(scrollContainer)) {
      document.body.removeChild(scrollContainer);
    }
  });

  it('should be hidden initially', () => {
    fixture.detectChanges();
    expect(component.visible).toBe(false);
    const btn = fixture.debugElement.query(By.css('.scroll-btn'));
    expect(btn).toBeNull();
  });

  it('should become visible after scrolling past threshold', fakeAsync(() => {
    fixture.detectChanges();
    
    scrollContainer.scrollTop = 400;
    scrollContainer.dispatchEvent(new Event('scroll'));
    
    // onScroll uses requestAnimationFrame
    tick(100); 
    fixture.detectChanges();
    
    expect(component.visible).toBe(true);
    const btn = fixture.debugElement.query(By.css('.scroll-btn'));
    expect(btn).toBeTruthy();
  }));

  it('should scroll to top when clicked', fakeAsync(() => {
    const scrollToSpy = vi.spyOn(scrollContainer, 'scrollTo').mockReturnValue(undefined as never);
    component.visible = true;
    fixture.detectChanges();
    
    const btn = fixture.debugElement.query(By.css('.scroll-btn'));
    btn.nativeElement.click();
    
    expect(scrollToSpy).toHaveBeenCalled();
    const args = (scrollToSpy as unknown as Spy).mock.calls.at(-1)!;
    expect(args[0]).toEqual(expect.objectContaining({ top: 0 }));
  }));
});
