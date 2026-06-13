import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { routes } from '../../app.routes';
import { DEEP_LINK_CATALOG } from '../../core/routing/deep-link-catalog';
import { ErrorGeneratorComponent } from './error-generator.component';

describe('ErrorGeneratorComponent', () => {
  let component: ErrorGeneratorComponent;
  let fixture: ComponentFixture<ErrorGeneratorComponent>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ErrorGeneratorComponent, NoopAnimationsModule],
      providers: [provideHttpClient(withXhr()), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(ErrorGeneratorComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('renders one card with five explained action buttons', () => {
    expect(fixture.debugElement.queryAll(By.css('mat-card')).length).toBe(1);

    const buttons = fixture.debugElement.queryAll(By.css('button[mat-raised-button]'));
    expect(buttons.length).toBe(5);
    expect(buttons.every((button) => button.attributes['matTooltip'])).toBe(true);
  });

  it('throws the uncaught smoke error on demand', () => {
    expect(() => component.triggerUncaught()).toThrowError('Slice 3 uncaught smoke');
  });

  it('creates the rejected-promise smoke error on demand', async () => {
    await expect(component.triggerRejection()).rejects.toThrow('Slice 3 rejection smoke');
  });

  it('requests a unique missing API path for network smoke', () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('00000000-0000-4000-8000-000000000003');

    component.triggerNetwork();

    const req = httpMock.expectOne('/api/__nonexistent_00000000-0000-4000-8000-000000000003');
    expect(req.request.method).toBe('GET');
    req.flush({});
  });

  it('writes the console smoke message', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockReturnValue(undefined as never);

    component.triggerConsole();

    expect(consoleSpy).toHaveBeenCalledWith('Slice 3 console smoke');
  });

  it('temporarily shifts the page and then restores it', fakeAsync(() => {
    const originalMargin = document.body.style.marginTop;

    component.triggerCls();
    tick(600);
    expect(document.body.style.marginTop).toBe('200px');

    tick(100);
    expect(document.body.style.marginTop).toBe(originalMargin);
  }));
});

describe('dev error-generator route registration', () => {
  it('registers the development-only route before the wildcard route', () => {
    const devRouteIndex = routes.findIndex((route) => route.path === 'dev/error-generator');
    const wildcardIndex = routes.findIndex((route) => route.path === '**');

    expect(devRouteIndex).toBeGreaterThanOrEqual(0);
    expect(wildcardIndex).toBeGreaterThan(devRouteIndex);
  });

  it('registers the route in the deep-link catalog', () => {
    expect(DEEP_LINK_CATALOG.some((entry) => entry.route === '/dev/error-generator')).toBe(true);
  });
});
