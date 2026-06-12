import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { SyncActivityComponent } from './sync-activity.component';
import { SyncService, SyncJob } from '../../jobs/sync.service';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { of } from 'rxjs';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';

describe('SyncActivityComponent', () => {
  let component: SyncActivityComponent;
  let fixture: ComponentFixture<SyncActivityComponent>;
  let mockSync: SpyObj<SyncService>;
  let mockVisibility: SpyObj<VisibilityGateService>;

  const mockJobs: SyncJob[] = [
    {
      job_id: '1', source: 'api', status: 'running', items_synced: 10, items_updated: 5,
      mode: 'full', progress: 10, message: 'Syncing...',
      ml_items_queued: 0, ml_items_completed: 0, spacy_items_completed: 0, embedding_items_completed: 0,
      checkpoint_stage: 'ingest', checkpoint_items_processed: 10, is_resumable: true,
      started_at: new Date().toISOString(), created_at: new Date().toISOString()
    },
    {
      job_id: '2', source: 'jsonl', status: 'failed', error_message: 'Format error',
      items_synced: 0, items_updated: 0, mode: 'incremental', progress: 0, message: 'Failed',
      ml_items_queued: 0, ml_items_completed: 0, spacy_items_completed: 0, embedding_items_completed: 0,
      checkpoint_stage: 'ingest', checkpoint_items_processed: 0, is_resumable: true,
      started_at: new Date().toISOString(), created_at: new Date().toISOString()
    }
  ];

  beforeEach(async () => {
    mockSync = createSpyObj(['getJobs', 'resumeJob']);
    mockVisibility = createSpyObj(['whileLoggedInAndVisible']);

    mockVisibility.whileLoggedInAndVisible.mockImplementation((fn) => fn());
    mockSync.getJobs.mockReturnValue(of(mockJobs));

    await TestBed.configureTestingModule({
      imports: [SyncActivityComponent, NoopAnimationsModule, MatSnackBarModule],
      providers: [
        { provide: SyncService, useValue: mockSync },
        { provide: VisibilityGateService, useValue: mockVisibility },
        provideRouter([])
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(SyncActivityComponent);
    component = fixture.componentInstance;
  });

  it('should create', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    expect(component).toBeTruthy();
  }));

  it('should list running and stuck jobs', fakeAsync(() => {
    component.jobs.set(mockJobs);
    fixture.detectChanges();
    
    expect(component.runningVisible().length).toBe(1);
    expect(component.stuckVisible().length).toBe(1);
    
    const rows = fixture.nativeElement.querySelectorAll('.sa-row');
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('XenForo');
    expect(rows[1].textContent).toContain('JSONL upload');
  }));

  it('should identify stuck reason', fakeAsync(() => {
    component.jobs.set(mockJobs);
    fixture.detectChanges();
    
    const failedJob = component.jobs()[1];
    expect(component.stuckReason(failedJob)).toContain('failed — Format error');
    
    // Test 1h logic
    const stuckJob: SyncJob = { 
      ...component.jobs()[0], 
      status: 'running', 
      started_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString() 
    };
    expect(component.stuckReason(stuckJob)).toBe('no progress in the last hour');
  }));

  it('should call resumeJob when restart is clicked', fakeAsync(() => {
    component.jobs.set(mockJobs);
    fixture.detectChanges();
    
    mockSync.resumeJob.mockReturnValue(of({ job_id: '2', status: 'pending', is_resumable: true }));
    const restartBtn = fixture.nativeElement.querySelector('.sa-fix');
    expect(restartBtn).toBeTruthy();
    restartBtn.click();
    
    expect(mockSync.resumeJob).toHaveBeenCalledWith('2');
  }));

  it('should show empty state when no jobs', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    component.jobs.set([]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.sa-empty')).toBeTruthy();
  }));
});
