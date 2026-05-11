import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { NotFoundComponent } from './not-found.component';

describe('NotFoundComponent', () => {
  let fixture: ComponentFixture<NotFoundComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NotFoundComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(NotFoundComponent);
    fixture.detectChanges();
  });

  it('renders the page-not-found heading', () => {
    expect(fixture.nativeElement.textContent).toContain('Page not found');
  });

  it('renders the descriptive body copy', () => {
    expect(fixture.nativeElement.textContent).toContain("doesn't exist or has been moved");
  });

  it('renders a link to the dashboard', () => {
    const link = fixture.nativeElement.querySelector('a[routerLink]');
    expect(link).toBeTruthy();
    expect(link.textContent.trim()).toBe('Go to Dashboard');
  });
});
