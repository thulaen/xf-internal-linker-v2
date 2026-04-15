import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { SyncService } from './sync.service';

describe('SyncService', () => {
  let service: SyncService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(SyncService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('posts pause and resume actions to the sync job endpoints', () => {
    service.pauseJob('job-1').subscribe();
    const pauseReq = http.expectOne('/api/sync-jobs/job-1/pause/');
    expect(pauseReq.request.method).toBe('POST');
    pauseReq.flush({ job_id: 'job-1', status: 'paused', is_resumable: true });

    service.resumeJob('job-1').subscribe();
    const resumeReq = http.expectOne('/api/sync-jobs/job-1/resume/');
    expect(resumeReq.request.method).toBe('POST');
    resumeReq.flush({ job_id: 'job-1', status: 'pending', is_resumable: true });
  });
});
