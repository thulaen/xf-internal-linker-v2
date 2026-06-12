import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { MatSnackBarModule, MatSnackBar } from '@angular/material/snack-bar';
import { WatchedPagesComponent } from './watched-pages.component';
import { By } from '@angular/platform-browser';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('WatchedPagesComponent', () => {
  let component: WatchedPagesComponent;
  let fixture: ComponentFixture<WatchedPagesComponent>;
  let httpMock: HttpTestingController;
  let snackBar: MatSnackBar;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        WatchedPagesComponent,
        HttpClientTestingModule,
        MatSnackBarModule,
        NoopAnimationsModule
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(WatchedPagesComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    snackBar = fixture.debugElement.injector.get(MatSnackBar);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create', () => {
    fixture.detectChanges();
    httpMock.expectOne('/api/analytics/watched-pages/').flush([]);
    expect(component).toBeTruthy();
  });

  it('should load watched pages on init', () => {
    const mockPages = [
      { id: 1, content_item_id: 10, title: 'Watched 1', url: '/w1', added_at: '2026-01-01', notes: 'Note 1' },
      { id: 2, content_item_id: 11, title: 'Watched 2', url: '/w2', added_at: '2026-01-02', notes: '' }
    ];

    fixture.detectChanges();
    const req = httpMock.expectOne('/api/analytics/watched-pages/');
    req.flush(mockPages);
    fixture.detectChanges();

    expect(component.loading()).toBe(false);
    expect(component.pages().length).toBe(2);
    const cards = fixture.nativeElement.querySelectorAll('.watch-card');
    expect(cards.length).toBe(2);
  });

  it('should remove page on remove() and show snackbar', fakeAsync(() => {
    const mockPages = [{ id: 1, content_item_id: 10, title: 'Watched 1', url: '/w1', added_at: '2026-01-01', notes: '' }];
    fixture.detectChanges();
    httpMock.expectOne('/api/analytics/watched-pages/').flush(mockPages);
    fixture.detectChanges();
    tick();

    vi.spyOn(snackBar, 'open').mockReturnValue(undefined as never);

    const removeBtn = fixture.debugElement.query(By.css('button[mat-icon-button]'));
    if (!removeBtn) throw new Error('Remove button not found');
    removeBtn.triggerEventHandler('click', null);
    tick();

    expect(component.removingId()).toBe(1);

    const delReq = httpMock.expectOne('/api/analytics/watched-pages/1/');
    expect(delReq.request.method).toBe('DELETE');
    delReq.flush({ success: true });

    fixture.detectChanges();
    tick();

    expect(component.removingId()).toBeNull();
    expect(component.pages().length).toBe(0);
    expect(snackBar.open).toHaveBeenCalled();
  }));

  it('should show error snackbar on remove() failure', fakeAsync(() => {
    const mockPages = [{ id: 1, content_item_id: 10, title: 'Watched 1', url: '/w1', added_at: '2026-01-01', notes: '' }];
    fixture.detectChanges();
    httpMock.expectOne('/api/analytics/watched-pages/').flush(mockPages);
    fixture.detectChanges();
    tick();

    vi.spyOn(snackBar, 'open').mockReturnValue(undefined as never);

    component.remove(mockPages[0]);
    tick();

    const delReq = httpMock.expectOne('/api/analytics/watched-pages/1/');
    delReq.error(new ProgressEvent('error'));

    fixture.detectChanges();
    tick();

    expect(component.removingId()).toBeNull();
    expect(snackBar.open).toHaveBeenCalled();
  }));
});
