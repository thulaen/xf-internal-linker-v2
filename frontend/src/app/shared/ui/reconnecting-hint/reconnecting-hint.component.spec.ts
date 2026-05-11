import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { BehaviorSubject } from 'rxjs';

import { RealtimeService } from '../../../core/services/realtime.service';
import { ConnectionStatus } from '../../../core/services/realtime.types';
import { ReconnectingHintComponent } from './reconnecting-hint.component';

describe('ReconnectingHintComponent', () => {
  let fixture: ComponentFixture<ReconnectingHintComponent>;
  let status$: BehaviorSubject<ConnectionStatus>;

  beforeEach(async () => {
    status$ = new BehaviorSubject<ConnectionStatus>('connected');

    await TestBed.configureTestingModule({
      imports: [ReconnectingHintComponent],
      providers: [
        {
          provide: RealtimeService,
          useValue: { connectionStatus$: status$.asObservable() },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ReconnectingHintComponent);
    fixture.detectChanges();
  });

  it('renders nothing while connected', () => {
    expect(fixture.debugElement.query(By.css('.rc-hint'))).toBeNull();
  });

  it('renders the reconnecting hint', () => {
    status$.next('reconnecting');
    fixture.detectChanges();

    const hint = fixture.debugElement.query(By.css('.rc-hint'));
    const icon = fixture.debugElement.query(By.css('mat-icon'));

    expect(hint.nativeElement.classList).toContain('rc-reconnecting');
    expect(hint.nativeElement.textContent).toContain('Reconnecting');
    expect(icon.nativeElement.textContent.trim()).toBe('sync');
  });

  it('renders the offline hint', () => {
    status$.next('offline');
    fixture.detectChanges();

    const hint = fixture.debugElement.query(By.css('.rc-hint'));
    const icon = fixture.debugElement.query(By.css('mat-icon'));

    expect(hint.nativeElement.classList).toContain('rc-offline');
    expect(hint.nativeElement.textContent).toContain('Offline');
    expect(icon.nativeElement.textContent.trim()).toBe('cloud_off');
  });
});
