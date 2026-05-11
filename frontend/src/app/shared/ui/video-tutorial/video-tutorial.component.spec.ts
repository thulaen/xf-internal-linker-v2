import { ComponentFixture, TestBed } from '@angular/core/testing';
import { VideoTutorialComponent } from './video-tutorial.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('VideoTutorialComponent', () => {
  let component: VideoTutorialComponent;
  let fixture: ComponentFixture<VideoTutorialComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [VideoTutorialComponent, NoopAnimationsModule]
    }).compileComponents();

    fixture = TestBed.createComponent(VideoTutorialComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render nothing if videoUrl is empty', () => {
    component.videoUrl = '';
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent.trim()).toBe('');
  });

  it('should render trigger button if videoUrl is provided', () => {
    component.videoUrl = 'test.mp4';
    component.title = 'Test Tutorial';
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.vt-trigger');
    expect(button).toBeTruthy();
    expect(button.textContent).toContain('Test Tutorial');
  });

  it('should show video when trigger is clicked', () => {
    component.videoUrl = 'test.mp4';
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.vt-trigger').click();
    fixture.detectChanges();

    const video = fixture.nativeElement.querySelector('video');
    expect(video).toBeTruthy();
    expect(video.src).toContain('test.mp4');
  });

  it('should hide video when close is clicked', () => {
    component.videoUrl = 'test.mp4';
    component.play();
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.vt-close').click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('video')).toBeFalsy();
    expect(fixture.nativeElement.querySelector('.vt-trigger')).toBeTruthy();
  });
});
