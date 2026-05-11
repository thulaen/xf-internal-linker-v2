import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

import { ServerErrorComponent } from './server-error.component';

describe('ServerErrorComponent', () => {
  let component: ServerErrorComponent;
  let fixture: ComponentFixture<ServerErrorComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ServerErrorComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(ServerErrorComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders the error heading with role="alert"', () => {
    const container = fixture.debugElement.query(By.css('.server-error-container'));
    expect(container.nativeElement.getAttribute('role')).toBe('alert');
    expect(fixture.nativeElement.textContent).toContain('Something went wrong');
  });

  it('renders the Try again button', () => {
    const buttons = fixture.debugElement.queryAll(By.css('button'));
    const reloadBtn = buttons.find(b => b.nativeElement.textContent.includes('Try again'));
    expect(reloadBtn).toBeTruthy();
  });

  it('renders the Go to Dashboard link', () => {
    const link = fixture.nativeElement.querySelector('a[routerLink]');
    expect(link).toBeTruthy();
    expect(link.textContent.trim()).toBe('Go to Dashboard');
  });

  it('exposes an onReload method', () => {
    expect(typeof component.onReload).toBe('function');
  });
});
