import {
  ComponentFixture,
  TestBed,
  discardPeriodicTasks,
  fakeAsync,
  tick,
} from '@angular/core/testing';
import { TypingIndicatorComponent } from './typing-indicator.component';
import { AuthService, AuthUser } from '../../../core/services/auth.service';
import { RealtimeService } from '../../../core/services/realtime.service';
import { of, Subject } from 'rxjs';
import { CommonModule } from '@angular/common';

describe('TypingIndicatorComponent', () => {
  let component: TypingIndicatorComponent;
  let fixture: ComponentFixture<TypingIndicatorComponent>;
  let authMock: jasmine.SpyObj<AuthService>;
  let realtimeMock: jasmine.SpyObj<RealtimeService>;
  let realtimeSubject: Subject<any>;

  beforeEach(async () => {
    authMock = jasmine.createSpyObj('AuthService', [], {
      currentUser$: of({
        id: 1,
        username: 'alice',
        email: 'alice@example.com',
        is_staff: true,
        date_joined: new Date().toISOString()
      } as AuthUser)
    });
    realtimeSubject = new Subject();
    realtimeMock = jasmine.createSpyObj('RealtimeService', ['subscribeTopic', 'publish']);
    realtimeMock.subscribeTopic.and.returnValue(realtimeSubject);

    await TestBed.configureTestingModule({
      imports: [TypingIndicatorComponent, CommonModule],
      providers: [
        { provide: AuthService, useValue: authMock },
        { provide: RealtimeService, useValue: realtimeMock }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(TypingIndicatorComponent);
    component = fixture.componentInstance;
    component.topic = 'typing.test';
  });

  it('should create', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should not show anything initially', () => {
    expect(fixture.nativeElement.querySelector('.ti')).toBeFalsy();
  });

  it('should show typing notice when a peer types', fakeAsync(() => {
    fixture.detectChanges();
    realtimeSubject.next({
      payload: {
        _publisher: { username: 'bob', connection_id: 'conn-1' }
      }
    });
    fixture.detectChanges();

    const text = fixture.nativeElement.querySelector('.ti-text');
    expect(text.textContent).toBe('bob is editing…');
  }));

  it('should show "bob and charlie are editing…" when two peers type', fakeAsync(() => {
    fixture.detectChanges();
    realtimeSubject.next({
      payload: { _publisher: { username: 'bob', connection_id: 'conn-1' } }
    });
    realtimeSubject.next({
      payload: { _publisher: { username: 'charlie', connection_id: 'conn-2' } }
    });
    fixture.detectChanges();

    const text = fixture.nativeElement.querySelector('.ti-text');
    expect(text.textContent).toBe('bob and charlie are editing…');
  }));

  it('should publish typing event on host input', () => {
    fixture.detectChanges();
    fixture.nativeElement.dispatchEvent(new Event('input'));
    expect(realtimeMock.publish).toHaveBeenCalledWith('typing.test', 'typing', { username: 'alice' });
  });

  it('should throttle publishing', fakeAsync(() => {
    fixture.detectChanges();
    fixture.nativeElement.dispatchEvent(new Event('input'));
    fixture.nativeElement.dispatchEvent(new Event('input'));
    expect(realtimeMock.publish).toHaveBeenCalledTimes(1);

    tick(1501); // Throttled for 1500ms
    fixture.nativeElement.dispatchEvent(new Event('input'));
    expect(realtimeMock.publish).toHaveBeenCalledTimes(2);
  }));

  it('should hide stale notices', fakeAsync(() => {
    fixture.detectChanges();
    realtimeSubject.next({
      payload: { _publisher: { username: 'bob', connection_id: 'conn-1' } }
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.ti')).toBeTruthy();

    // Fast-forward way past the stale timeout (4000ms)
    tick(10000);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.ti')).toBeFalsy();
    discardPeriodicTasks();
  }));
});
