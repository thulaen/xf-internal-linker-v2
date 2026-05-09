import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { FeatureRequestService } from './feature-request.service';

describe('FeatureRequestService', () => {
  let service: FeatureRequestService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        FeatureRequestService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Router, useValue: { url: '/dashboard' } },
      ],
    });
    service = TestBed.inject(FeatureRequestService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('list() with no status arg GETs the bare endpoint', () => {
    service.list().subscribe();
    const req = httpMock.expectOne('/api/feature-requests/');
    expect(req.request.method).toBe('GET');
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('list(status) appends an encoded status query parameter', () => {
    service.list('shipped').subscribe();
    const req = httpMock.expectOne('/api/feature-requests/?status=shipped');
    expect(req.request.method).toBe('GET');
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('submit() POSTs the payload + auto-captured context', () => {
    service
      .submit({ title: 'Add foo', body: 'Please add a foo button', category: 'ui' })
      .subscribe();
    const req = httpMock.expectOne('/api/feature-requests/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.title).toBe('Add foo');
    expect(req.request.body.body).toBe('Please add a foo button');
    expect(req.request.body.category).toBe('ui');
    expect(req.request.body.priority).toBe('medium'); // default
    expect(req.request.body.context.route).toBe('/dashboard');
    expect(typeof req.request.body.context.client_submitted_at).toBe('string');
    req.flush({} as any);
  });

  it('submit() defaults category to "" and priority to "medium" when omitted', () => {
    service.submit({ title: 't', body: 'b' }).subscribe();
    const req = httpMock.expectOne('/api/feature-requests/');
    expect(req.request.body.category).toBe('');
    expect(req.request.body.priority).toBe('medium');
    req.flush({} as any);
  });

  it('submit() respects an explicit priority override', () => {
    service.submit({ title: 't', body: 'b', priority: 'high' }).subscribe();
    const req = httpMock.expectOne('/api/feature-requests/');
    expect(req.request.body.priority).toBe('high');
    req.flush({} as any);
  });

  it('vote(id) POSTs to the vote action endpoint', () => {
    service.vote(7).subscribe();
    const req = httpMock.expectOne('/api/feature-requests/7/vote/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush({ votes: 5, has_voted: true });
  });

  it('unvote(id) POSTs to the unvote action endpoint', () => {
    service.unvote(7).subscribe();
    const req = httpMock.expectOne('/api/feature-requests/7/unvote/');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush({ votes: 4, has_voted: false });
  });
});
