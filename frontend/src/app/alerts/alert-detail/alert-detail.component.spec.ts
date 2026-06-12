import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';
import { AlertDetailComponent } from './alert-detail.component';
import { NotificationService, OperatorAlert } from '../../core/services/notification.service';

const MOCK_ALERT: OperatorAlert = {
  id: 'a1',
  title: 'Test Alert',
  message: 'Something went wrong',
  severity: 'error',
  event_type: 'pipeline.failed',
  source_area: 'pipeline',
  status: 'open',
  occurrence_count: 3,
  first_seen_at: '2026-01-01T00:00:00Z',
  last_seen_at: '2026-01-02T00:00:00Z',
  suppressed_until: null,
  related_route: null,
} as unknown as OperatorAlert;

/** Creates a minimal ActivatedRoute mock for testing. */
const makeRoute = (id: string | null) => ({
  snapshot: {
    paramMap: { get: (key: string) => (key === 'id' ? id : null) },
  },
});

describe('AlertDetailComponent', () => {
  let fixture: ComponentFixture<AlertDetailComponent>;
  let component: AlertDetailComponent;
  let notifSpy: SpyObj<NotificationService>;

  beforeEach(async () => {
    notifSpy = createSpyObj(['getAlert']);
    notifSpy.getAlert.mockReturnValue(of(MOCK_ALERT));

    await TestBed.configureTestingModule({
      imports: [AlertDetailComponent],
      providers: [
        provideNoopAnimations(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: makeRoute('a1') },
        { provide: NotificationService, useValue: notifSpy },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AlertDetailComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders the alert card when alert loads successfully', () => {
    const card = fixture.nativeElement.querySelector('mat-card');
    expect(card).toBeTruthy();
  });

  it('calls getAlert with the route id', () => {
    expect(notifSpy.getAlert).toHaveBeenCalledWith('a1');
    expect(notifSpy.getAlert).toHaveBeenCalledTimes(1);
  });

  it('sets loading to false after data arrives', () => {
    expect(component.loading).toBe(false);
  });

  it('displays the alert title in the card', () => {
    const title = fixture.nativeElement.querySelector('mat-card-title');
    expect(title?.textContent?.trim()).toBe('Test Alert');
  });

  it('has no loadError when alert is present', () => {
    expect(component.loadError).toBeNull();
  });

  it('sets loadError and no-loading when the route has no id', async () => {
    // Use a fresh spy so call history from other tests does not bleed in.
    const freshSpy = createSpyObj<NotificationService>(['getAlert']);

    await TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [AlertDetailComponent],
      providers: [
        provideNoopAnimations(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: makeRoute(null) },
        { provide: NotificationService, useValue: freshSpy },
      ],
    }).compileComponents();

    const f2 = TestBed.createComponent(AlertDetailComponent);
    f2.detectChanges();

    expect(f2.componentInstance.loadError).toBeTruthy();
    expect(f2.componentInstance.loading).toBe(false);
    // getAlert must NOT have been called — there's no id to fetch.
    expect(freshSpy.getAlert).not.toHaveBeenCalled();
  });
});
