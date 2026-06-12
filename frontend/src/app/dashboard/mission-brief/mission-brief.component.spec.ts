import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { MissionBriefComponent } from './mission-brief.component';
import { DashboardService } from '../dashboard.service';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';

describe('MissionBriefComponent', () => {
  let component: MissionBriefComponent;
  let fixture: ComponentFixture<MissionBriefComponent>;
  let mockDash: any;
  let mockVisibility: any;

  beforeEach(async () => {
    mockDash = {
      getMissionBrief: vi.fn().mockReturnValue(of({
        sentences: ['Yesterday was busy.', 'Today is quiet.', 'Watch out for issues.'],
        top_alert: null
      }))
    };

    mockVisibility = {
      whileLoggedInAndVisible: vi.fn().mockImplementation((fn: any) => fn())
    };

    await TestBed.configureTestingModule({
      imports: [MissionBriefComponent],
      providers: [
        provideRouter([]),
        { provide: DashboardService, useValue: mockDash },
        { provide: VisibilityGateService, useValue: mockVisibility }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(MissionBriefComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should load and display the brief', fakeAsync(() => {
    fixture.detectChanges(); // Trigger ngOnInit
    tick(); // timer(0)
    fixture.detectChanges(); // Update OnPush template

    const compiled = fixture.nativeElement as HTMLElement;
    const sentences = compiled.querySelectorAll('.mb-sentence span');
    expect(sentences.length).toBe(3);
    expect(sentences[0].textContent).toContain('Yesterday was busy.');
  }));

  it('should show alert link when top_alert exists', fakeAsync(() => {
    mockDash.getMissionBrief.mockReturnValue(of({
      sentences: ['S1', 'S2', 'S3'],
      top_alert: { alert_id: 'A1' }
    }));

    // Re-trigger initialization to use the new mock value
    component.ngOnInit();
    tick();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.mb-alert-link')).toBeTruthy();
    expect(compiled.querySelector('.mb-sentence:nth-child(3)')?.classList).toContain('mb-watch');
  }));
});
