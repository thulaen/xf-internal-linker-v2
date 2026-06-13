import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { SafePruneCardComponent } from './safe-prune-card.component';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { By } from '@angular/platform-browser';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('SafePruneCardComponent', () => {
  let component: SafePruneCardComponent;
  let fixture: ComponentFixture<SafePruneCardComponent>;
  let httpMock: HttpTestingController;
  let snackBarSpy: SpyObj<MatSnackBar>;

  beforeEach(async () => {
    snackBarSpy = createSpyObj(['open']);

    await TestBed.configureTestingModule({
      imports: [SafePruneCardComponent, NoopAnimationsModule],
      providers: [provideHttpClient(withXhr()), provideHttpClientTesting()],
    })
      .overrideComponent(SafePruneCardComponent, {
        set: { providers: [{ provide: MatSnackBar, useValue: snackBarSpy }] },
      })
      .compileComponents();

    fixture = TestBed.createComponent(SafePruneCardComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should load status on init', fakeAsync(() => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/prune/safe/');
    req.flush({
      allowed_targets: [{ id: 'test', label: 'Test', detail: 'Detail', approx_reclaim_mb: 10 }],
      deny_list: ['secrets'],
      idle: true,
      notes: [],
    });

    tick();
    fixture.detectChanges();
    expect(component.loading()).toBe(false);
    expect(component.status()?.allowed_targets.length).toBe(1);
    const label = fixture.debugElement.query(By.css('.target-label'));
    expect(label.nativeElement.textContent).toContain('Test');
  }));

  it('should run preview and show snackbar', fakeAsync(() => {
    fixture.detectChanges();
    const initReq = httpMock.expectOne('/api/prune/safe/');
    initReq.flush({
      allowed_targets: [{ id: 'test', label: 'Test', detail: 'Detail', approx_reclaim_mb: 10 }],
      deny_list: [],
      idle: true,
      notes: [],
    });
    tick();
    fixture.detectChanges();

    const previewBtn = fixture.debugElement.query(By.css('button[mat-stroked-button]'));
    previewBtn.nativeElement.click();

    const previewReq = httpMock.expectOne('/api/prune/safe/');
    expect(previewReq.request.method).toBe('POST');
    expect(previewReq.request.body).toEqual({ target: 'test' });
    previewReq.flush({ ok: true, estimated_reclaim_mb: 15 });

    tick();
    expect(component.busyTarget()).toBe('');
    expect(snackBarSpy.open).toHaveBeenCalledWith(expect.stringMatching(/Preview: ~15 MB/), 'OK', expect.any(Object));
  }));

  it('should commit prune after confirmation', fakeAsync(() => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    fixture.detectChanges();
    const initReq = httpMock.expectOne('/api/prune/safe/');
    initReq.flush({
      allowed_targets: [{ id: 'test', label: 'Test', detail: 'Detail', approx_reclaim_mb: 10 }],
      deny_list: [],
      idle: true,
      notes: [],
    });
    tick();
    fixture.detectChanges();

    const pruneBtn = fixture.debugElement.query(By.css('button[mat-flat-button]'));
    pruneBtn.nativeElement.click();

    const commitReq = httpMock.expectOne('/api/prune/safe/');
    expect(commitReq.request.body).toEqual({ target: 'test', confirmed: true });
    commitReq.flush({ ok: true, reclaimed_mb: 15 });

    // After commit success, it reloads status
    const reloadReq = httpMock.expectOne('/api/prune/safe/');
    reloadReq.flush({ allowed_targets: [], deny_list: [], idle: true, notes: [] });

    tick();
    expect(component.busyTarget()).toBe('');
    expect(snackBarSpy.open).toHaveBeenCalledWith(expect.stringMatching(/Pruned test/), 'OK', expect.any(Object));
  }));

  it('should disable prune button if system is not idle', fakeAsync(() => {
    fixture.detectChanges();
    const req = httpMock.expectOne('/api/prune/safe/');
    req.flush({
      allowed_targets: [{ id: 'test', label: 'Test', detail: 'Detail', approx_reclaim_mb: 10 }],
      deny_list: [],
      idle: false,
      notes: [],
    });

    tick();
    fixture.detectChanges();
    const pruneBtn = fixture.debugElement.query(By.css('button[mat-flat-button]'));
    expect(pruneBtn.nativeElement.disabled).toBe(true);
  }));
});
