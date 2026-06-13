import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { WhosOnShiftComponent } from './whos-on-shift.component';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { AuthService } from '../../core/services/auth.service';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';
import { BehaviorSubject, take, Observable } from 'rxjs';
import { By } from '@angular/platform-browser';

describe('WhosOnShiftComponent', () => {
  let component: WhosOnShiftComponent;
  let fixture: ComponentFixture<WhosOnShiftComponent>;
  let httpMock: HttpTestingController;
  let authServiceSpy: { currentUser$: BehaviorSubject<any> };
  let visibilityGateSpy: { whileLoggedInAndVisible: Spy };

  beforeEach(async () => {
    authServiceSpy = {
      currentUser$: new BehaviorSubject({ username: 'testuser' }),
    };
    visibilityGateSpy = {
      whileLoggedInAndVisible: vi.fn().mockImplementation((fn: () => Observable<any>) => {
        return fn().pipe(take(1));
      }),
    };

    await TestBed.configureTestingModule({
      imports: [WhosOnShiftComponent],
      providers: [provideHttpClient(withXhr()), provideHttpClientTesting()],
    })
      .overrideComponent(WhosOnShiftComponent, {
        set: {
          providers: [
            { provide: AuthService, useValue: authServiceSpy },
            { provide: VisibilityGateService, useValue: visibilityGateSpy },
          ],
        },
      })
      .compileComponents();

    fixture = TestBed.createComponent(WhosOnShiftComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should remain hidden if no other users are active', fakeAsync(() => {
    fixture.detectChanges();
    expect(visibilityGateSpy.whileLoggedInAndVisible).toHaveBeenCalled();
    tick(100);
    const req = httpMock.expectOne((r) => r.url.includes('/api/auth/active-users/'));
    req.flush([{ username: 'testuser', last_seen: new Date().toISOString() }]);

    tick();
    fixture.detectChanges();
    expect(component.visible()).toBe(false);
    const card = fixture.debugElement.query(By.css('.ws-card'));
    expect(card).toBeNull();
  }));

  it('should show card if other users are active', fakeAsync(() => {
    fixture.detectChanges();
    tick(100);
    const req = httpMock.expectOne((r) => r.url.includes('/api/auth/active-users/'));
    req.flush([
      { username: 'testuser', last_seen: new Date().toISOString() },
      { username: 'otheruser', last_seen: new Date().toISOString() },
    ]);

    tick();
    fixture.detectChanges();
    expect(component.visible()).toBe(true);
    const rows = fixture.debugElement.queryAll(By.css('.ws-row'));
    expect(rows.length).toBe(2);
    expect(rows[1].nativeElement.textContent).toContain('otheruser');
  }));

  it('should hide card if endpoint fails (404)', fakeAsync(() => {
    fixture.detectChanges();
    tick(100);
    const req = httpMock.expectOne((r) => r.url.includes('/api/auth/active-users/'));
    req.error(new ErrorEvent('Not Found'), { status: 404 });

    tick();
    fixture.detectChanges();
    expect(component.visible()).toBe(false);
  }));

  it('should format "ago" correctly', () => {
    const now = new Date();
    const oneMinAgo = new Date(now.getTime() - 61000).toISOString();
    const justNow = now.toISOString();

    expect(component.ago(justNow)).toBe('now');
    expect(component.ago(oneMinAgo)).toBe('1m ago');
  });
});
