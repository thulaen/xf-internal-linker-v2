import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { MatSnackBarModule, MatSnackBar } from '@angular/material/snack-bar';
import { UnderLinkedComponent } from './under-linked.component';
import { By } from '@angular/platform-browser';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('UnderLinkedComponent', () => {
  let component: UnderLinkedComponent;
  let fixture: ComponentFixture<UnderLinkedComponent>;
  let httpMock: HttpTestingController;
  let snackBar: MatSnackBar;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        UnderLinkedComponent,
        HttpClientTestingModule,
        MatSnackBarModule,
        NoopAnimationsModule
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(UnderLinkedComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    snackBar = fixture.debugElement.injector.get(MatSnackBar);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create', () => {
    fixture.detectChanges();
    httpMock.expectOne('/api/graph/gap-analysis/').flush([]);
    expect(component).toBeTruthy();
  });

  it('should load gap rows on init', () => {
    const mockRows = [
      { content_item_id: 1, title: 'Page 1', url: '/p1', opportunity_score: 80, incoming_link_count: 1 },
      { content_item_id: 2, title: 'Page 2', url: '/p2', opportunity_score: 40, incoming_link_count: 2 }
    ];

    fixture.detectChanges();
    const req = httpMock.expectOne('/api/graph/gap-analysis/');
    expect(req.request.method).toBe('GET');
    req.flush(mockRows);

    fixture.detectChanges();

    expect(component.loading()).toBeFalse();
    expect(component.rows().length).toBe(2);
    const cards = fixture.nativeElement.querySelectorAll('.gap-card');
    expect(cards.length).toBe(2);
  });

  it('should show empty state when no rows returned', () => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/graph/gap-analysis/');
    req.flush([]);

    fixture.detectChanges();

    expect(component.loading()).toBeFalse();
    const emptyState = fixture.nativeElement.querySelector('app-empty-state');
    expect(emptyState).toBeTruthy();
  });

  it('should call watch() and show success snackbar', fakeAsync(() => {
    const mockRows = [
      { content_item_id: 1, title: 'Page 1', url: '/p1', opportunity_score: 80, incoming_link_count: 1 }
    ];
    
    fixture.detectChanges();
    httpMock.expectOne('/api/graph/gap-analysis/').flush(mockRows);
    fixture.detectChanges();
    tick();

    spyOn(snackBar, 'open');

    const watchBtn = fixture.debugElement.query(By.css('.watch-btn'));
    if (!watchBtn) {
      throw new Error('Watch button not found. Current HTML: ' + fixture.nativeElement.innerHTML);
    }
    watchBtn.triggerEventHandler('click', null);
    tick();
    
    expect(component.watchingId()).toBe(1);

    const watchReq = httpMock.expectOne('/api/analytics/watched-pages/');
    expect(watchReq.request.method).toBe('POST');
    watchReq.flush({ success: true });

    fixture.detectChanges();
    tick();

    expect(component.watchingId()).toBeNull();
    expect(snackBar.open).toHaveBeenCalled();
  }));

  it('should show error snackbar on watch() failure', fakeAsync(() => {
    const mockRows = [
      { content_item_id: 1, title: 'Page 1', url: '/p1', opportunity_score: 80, incoming_link_count: 1 }
    ];
    
    fixture.detectChanges();
    httpMock.expectOne('/api/graph/gap-analysis/').flush(mockRows);
    fixture.detectChanges();
    tick();

    spyOn(snackBar, 'open');

    component.watch(mockRows[0]);
    tick();
    
    const watchReq = httpMock.expectOne('/api/analytics/watched-pages/');
    watchReq.error(new ProgressEvent('error'));

    fixture.detectChanges();
    tick();

    expect(component.watchingId()).toBeNull();
    expect(snackBar.open).toHaveBeenCalled();
  }));
});
