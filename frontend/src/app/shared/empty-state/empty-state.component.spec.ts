import { ComponentFixture, TestBed } from '@angular/core/testing';
import { EmptyStateComponent } from './empty-state.component';
import { RouterTestingModule } from '@angular/router/testing';
import { By } from '@angular/platform-browser';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

describe('EmptyStateComponent', () => {
  let fixture: ComponentFixture<EmptyStateComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EmptyStateComponent, RouterTestingModule, MatIconModule, MatButtonModule],
    }).compileComponents();

    fixture = TestBed.createComponent(EmptyStateComponent);
  });

  it('should render required inputs', () => {
    fixture.componentRef.setInput('icon', 'search');
    fixture.componentRef.setInput('heading', 'No results found');
    fixture.componentRef.setInput('body', 'Try adjusting your filters to find what you are looking for.');
    fixture.detectChanges();

    expect(fixture.debugElement.query(By.css('.empty-icon')).nativeElement.textContent).toBe('search');
    expect(fixture.debugElement.query(By.css('.empty-heading')).nativeElement.textContent).toBe('No results found');
    expect(fixture.debugElement.query(By.css('.empty-body')).nativeElement.textContent).toBe('Try adjusting your filters to find what you are looking for.');
  });

  it('should show optional example and CTA', () => {
    fixture.componentRef.setInput('icon', 'link_off');
    fixture.componentRef.setInput('heading', 'No broken links');
    fixture.componentRef.setInput('body', 'Your site is looking healthy.');
    fixture.componentRef.setInput('example', 'Last scan was 2 hours ago.');
    fixture.componentRef.setInput('ctaLabel', 'Run scan now');
    fixture.componentRef.setInput('ctaRoute', '/scan');
    fixture.detectChanges();

    const example = fixture.debugElement.query(By.css('.empty-example'));
    expect(example).toBeTruthy();
    expect(example.nativeElement.textContent).toBe('Last scan was 2 hours ago.');

    const cta = fixture.debugElement.query(By.css('.empty-cta'));
    expect(cta).toBeTruthy();
    expect(cta.nativeElement.textContent).toContain('Run scan now');
    expect(cta.nativeElement.getAttribute('href')).toBe('/scan');
  });

  it('should not show optional example or CTA if not provided', () => {
    fixture.componentRef.setInput('icon', 'info');
    fixture.componentRef.setInput('heading', 'Info');
    fixture.componentRef.setInput('body', 'Info body');
    fixture.detectChanges();

    expect(fixture.debugElement.query(By.css('.empty-example'))).toBeNull();
    expect(fixture.debugElement.query(By.css('.empty-cta'))).toBeNull();
  });
});
