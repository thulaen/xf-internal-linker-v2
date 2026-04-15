import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { PickUpComponent } from './pick-up.component';

describe('PickUpComponent', () => {
  let fixture: ComponentFixture<PickUpComponent>;
  let component: PickUpComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PickUpComponent, NoopAnimationsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(PickUpComponent);
    component = fixture.componentInstance;
  });

  it('renders backend resume fields and emits the sync job id', () => {
    component.resumeState = {
      interrupted_runs: [],
      missed_tasks: [],
      resumable_syncs: [
        {
          job_id: 'sync-1',
          status: 'failed',
          source: 'api',
          mode: 'full',
          checkpoint_stage: 'ingest',
          checkpoint_items_processed: 12,
        },
      ],
    };
    const emitted: string[] = [];
    component.resumeRun.subscribe((id) => emitted.push(id));

    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('API full');
    expect(text).toContain('ingest after 12 items');

    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    button.click();

    expect(emitted).toEqual(['sync-1']);
  });
});
