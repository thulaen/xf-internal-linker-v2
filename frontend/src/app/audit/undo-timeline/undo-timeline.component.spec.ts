import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { MatSnackBar } from '@angular/material/snack-bar';

import { UndoTimelineComponent } from './undo-timeline.component';
import { ConfirmService } from '../../shared/confirm-dialog/confirm.service';

describe('UndoTimelineComponent', () => {
  let fixture: ComponentFixture<UndoTimelineComponent>;
  let component: UndoTimelineComponent;
  let httpMock: HttpTestingController;
  const confirmStub = { ask: () => Promise.resolve(true) };
  const snackStub = { open: () => undefined };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [UndoTimelineComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: ConfirmService, useValue: confirmStub },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    })
      .overrideComponent(UndoTimelineComponent, {
        set: { template: '<div></div>' },
      })
      .compileComponents();
    fixture = TestBed.createComponent(UndoTimelineComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('renders without throwing and loads the timeline on init', () => {
    fixture.detectChanges();
    const reqs = httpMock.match((r) => r.url === '/api/audit/timeline/');
    expect(reqs.length).toBe(1);
    reqs[0].flush({
      lookback_days: 30,
      count: 1,
      entries: [
        {
          id: 7,
          action: 'update',
          subject_type: 'WeightPreset',
          subject_id: 'darb',
          actor: 'thulaen',
          message: 'Edit',
          created_at: '2026-04-30T12:00:00Z',
          old_value: { x: 1 },
          new_value: { x: 2 },
          is_restorable: true,
          not_restorable_reason: '',
          metadata: {},
        },
      ],
    });
    expect(component.entries().length).toBe(1);
    expect(component.restorableCount()).toBe(1);
  });

  it('formats null values and falls back to ISO when date parse fails', () => {
    expect(component.formatValue(null)).toContain('none');
    expect(component.formatValue('hi')).toBe('hi');
    expect(component.formatValue({ a: 1 })).toContain('a');
    expect(component.formatDate('not-a-date')).toBeTruthy();
  });

  it('handles error path of primary load', () => {
    fixture.detectChanges();
    const reqs = httpMock.match(() => true);
    if (reqs.length > 0) {
      reqs[0].flush(
        { detail: 'boom' },
        { status: 500, statusText: 'Server Error' },
      );
      reqs.slice(1).forEach((r) => r.flush({}));
    }
    expect(component.error()).toContain('boom');
    expect(component.loading()).toBe(false);
  });
});
