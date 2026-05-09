import { TestBed } from '@angular/core/testing';
import { AudioCueService } from './audio-cue.service';
import { OperatorAlert } from './notification.service';

describe('AudioCueService', () => {
  let service: AudioCueService;
  let playSpy: jasmine.Spy;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(AudioCueService);
    playSpy = spyOn(service, 'playTone');
  });

  function makeAlert(overrides: Partial<OperatorAlert> = {}): OperatorAlert {
    return {
      id: 1,
      alert_id: 'a',
      event_type: 'job_failed',
      source_area: 'pipeline',
      severity: 'error',
      status: 'unread',
      title: 't',
      message: 'm',
      dedupe_key: 'k',
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

  it('skips entirely while quiet hours are active', () => {
    service.playForAlert(makeAlert({ severity: 'urgent' }), 'info', /* quiet */ true);
    expect(playSpy).not.toHaveBeenCalled();
  });

  it('skips alerts below the configured minimum severity', () => {
    service.playForAlert(makeAlert({ severity: 'warning' }), 'error', false);
    expect(playSpy).not.toHaveBeenCalled();
  });

  it('plays the error tone for urgent alerts', () => {
    service.playForAlert(makeAlert({ severity: 'urgent' }), 'info', false);
    expect(playSpy).toHaveBeenCalledOnceWith('error');
  });

  it('plays the error tone for error alerts', () => {
    service.playForAlert(makeAlert({ severity: 'error' }), 'info', false);
    expect(playSpy).toHaveBeenCalledOnceWith('error');
  });

  it('plays the warning tone for warning alerts', () => {
    service.playForAlert(makeAlert({ severity: 'warning' }), 'info', false);
    expect(playSpy).toHaveBeenCalledOnceWith('warning');
  });

  it('plays the success tone for success alerts', () => {
    service.playForAlert(makeAlert({ severity: 'success' }), 'info', false);
    expect(playSpy).toHaveBeenCalledOnceWith('success');
  });

  it('does NOT play any tone for info alerts (info is below the chime ladder)', () => {
    service.playForAlert(makeAlert({ severity: 'info' }), 'info', false);
    expect(playSpy).not.toHaveBeenCalled();
  });

  it('falls back to rank 0 for an unknown alert severity (no tone)', () => {
    service.playForAlert(makeAlert({ severity: 'mystery' as never }), 'info', false);
    expect(playSpy).not.toHaveBeenCalled();
  });

  it('falls back to rank 3 for an unknown minSeverity (suppresses anything below error)', () => {
    service.playForAlert(makeAlert({ severity: 'warning' }), 'mystery' as never, false);
    expect(playSpy).not.toHaveBeenCalled();
  });

  describe('playTone()', () => {
    it('does not throw for any of the three tone types when AudioContext is available', () => {
      // Restore the real implementation for this nested describe.
      playSpy.and.callThrough();
      expect(() => service.playTone('success')).not.toThrow();
      expect(() => service.playTone('warning')).not.toThrow();
      expect(() => service.playTone('error')).not.toThrow();
    });
  });
});
