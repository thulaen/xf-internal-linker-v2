import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { FindBugsService } from './find-bugs.service';

describe('FindBugsService', () => {
  let service: FindBugsService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        FindBugsService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(FindBugsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('posts deliberate issue actions to the FindBugs backend endpoints', () => {
    service.confirmRealBug(7).subscribe();
    expectPost('/api/find-bugs/confirm/', { issue_id: 7 });

    service.evaluateWithAgents([7], 'codex').subscribe();
    expectPost('/api/find-bugs/evaluate/', { issue_ids: [7], agent: 'codex' });

    service.duplicateCheck(7).subscribe();
    expectPost('/api/find-bugs/duplicate-check/', { issue_id: 7 });

    service.regressionCheck(7).subscribe();
    expectPost('/api/find-bugs/regression-check/', { issue_id: 7 });

    service.createFixTask(7).subscribe();
    expectPost('/api/find-bugs/create-fix-task/', { issue_id: 7 });

    service.assignAgent(7, 'codex').subscribe();
    expectPost('/api/find-bugs/assign-agent/', { issue_id: 7, agent: 'codex' });

    service.approveLesson(7).subscribe();
    expectPost('/api/find-bugs/approve-lesson/', { issue_id: 7 });
  });

  it('posts report and context actions to bounded backend endpoints', () => {
    service.generateReport().subscribe();
    expectPost('/api/find-bugs/generate-report/', {});

    service.syncContext().subscribe();
    expectPost('/api/find-bugs/sync-context/', {});
  });

  function expectPost(url: string, body: unknown): void {
    const req = httpMock.expectOne(url);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(body);
    req.flush({ status: 'ok' });
  }
});
