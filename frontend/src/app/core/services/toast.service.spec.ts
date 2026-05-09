import { TestBed } from '@angular/core/testing';
import { MatSnackBar, MatSnackBarRef } from '@angular/material/snack-bar';
import { Subject } from 'rxjs';
import { OperatorAlert } from './notification.service';
import { ToastService } from './toast.service';

describe('ToastService', () => {
  let service: ToastService;
  let snackOpen: jasmine.Spy;
  let actionSubject: Subject<void>;
  let lastConfig: { duration?: number; panelClass?: string[] } | null;
  let lastAction: string | undefined;
  let lastMessage: string | undefined;

  beforeEach(() => {
    actionSubject = new Subject<void>();
    lastConfig = null;
    lastAction = undefined;
    lastMessage = undefined;

    const fakeRef: Partial<MatSnackBarRef<unknown>> = {
      onAction: () => actionSubject.asObservable(),
    };

    snackOpen = jasmine.createSpy('open').and.callFake(
      (message: string, action: string, config: { duration?: number; panelClass?: string[] } = {}) => {
        lastMessage = message;
        lastAction = action;
        lastConfig = config;
        return fakeRef as MatSnackBarRef<unknown>;
      },
    );

    TestBed.configureTestingModule({
      providers: [{ provide: MatSnackBar, useValue: { open: snackOpen } }],
    });
    service = TestBed.inject(ToastService);
  });

  function makeAlert(overrides: Partial<OperatorAlert> = {}): OperatorAlert {
    return {
      id: 1,
      alert_id: 'a',
      event_type: 'job_failed',
      source_area: 'pipeline',
      severity: 'warning',
      status: 'unread',
      title: 'Job failed',
      message: 'Sync failed',
      dedupe_key: 'd',
      occurrence_count: 1,
      related_object_type: '',
      related_object_id: '',
      related_route: '',
      payload: {},
      error_log_id: null,
      first_seen_at: '',
      last_seen_at: '',
      suppressed_until: null,
      read_at: null,
      acknowledged_at: null,
      resolved_at: null,
      created_at: '',
      updated_at: '',
      ...overrides,
    };
  }

  it('show() opens the snackbar with a default Dismiss action', () => {
    service.show('Hello');
    expect(snackOpen).toHaveBeenCalled();
    expect(lastMessage).toBe('Hello');
    expect(lastAction).toBe('Dismiss');
    expect(lastConfig?.duration).toBe(5000);
  });

  it('show() respects a custom action and duration', () => {
    service.show('Hi', 'OK', 1000);
    expect(lastAction).toBe('OK');
    expect(lastConfig?.duration).toBe(1000);
  });

  it('showForAlert() suppresses alerts below the minimum severity', () => {
    service.showForAlert(makeAlert({ severity: 'info' }), 'warning');
    expect(snackOpen).not.toHaveBeenCalled();
  });

  it('showForAlert() opens for alerts at or above the threshold', () => {
    service.showForAlert(makeAlert({ severity: 'warning' }), 'warning');
    expect(snackOpen).toHaveBeenCalledTimes(1);
    expect(lastMessage).toBe('Job failed');
    expect(lastAction).toBe('Dismiss'); // no related_route
    expect(lastConfig?.duration).toBe(6000);
    expect(lastConfig?.panelClass).toEqual(['toast-warning']);
  });

  it('showForAlert() uses "Go" as the action when related_route is set', () => {
    service.showForAlert(
      makeAlert({ severity: 'urgent', related_route: '/dashboard' }),
      'info',
    );
    expect(lastAction).toBe('Go');
    expect(lastConfig?.duration).toBe(10000);
    expect(lastConfig?.panelClass).toEqual(['toast-urgent']);
  });

  it('showForAlert() falls back to safe defaults for unknown severity strings', () => {
    service.showForAlert(makeAlert({ severity: 'mystery' as never }), 'info');
    expect(snackOpen).toHaveBeenCalledTimes(1);
    expect(lastConfig?.duration).toBe(5000); // fallback
    expect(lastConfig?.panelClass).toEqual(['toast-info']); // fallback
  });

  it('showForAlert() falls back to a 2-rank threshold for unknown minSeverity', () => {
    // Unknown minSeverity defaults rank to 2 (= "warning"), so an "info"
    // (rank 0) alert is suppressed.
    service.showForAlert(makeAlert({ severity: 'info' }), 'mystery' as never);
    expect(snackOpen).not.toHaveBeenCalled();
  });

  it('showUndo() opens with an "Undo" action and stays open for the requested duration', () => {
    service.showUndo('Deleted', () => undefined, 1000);
    expect(snackOpen).toHaveBeenCalled();
    expect(lastAction).toBe('Undo');
    expect(lastConfig?.duration).toBe(1000);
    expect(lastConfig?.panelClass).toEqual(['toast-undo']);
  });

  it('showUndo() invokes undoFn() exactly once when the user clicks the action', () => {
    const undo = jasmine.createSpy('undo');
    service.showUndo('Deleted', undo);
    actionSubject.next();
    expect(undo).toHaveBeenCalledTimes(1);
  });

  it('showUndo() swallows synchronous errors thrown by undoFn', () => {
    service.showUndo('Deleted', () => {
      throw new Error('boom');
    });
    expect(() => actionSubject.next()).not.toThrow();
  });

  it('showUndo() swallows promise rejections from async undoFn', (done) => {
    service.showUndo('Deleted', () => Promise.reject(new Error('boom')));
    expect(() => actionSubject.next()).not.toThrow();
    // Allow the rejection to be queued + caught; if it leaks, the test runner
    // surfaces it as an unhandled rejection.
    setTimeout(() => done(), 0);
  });
});
