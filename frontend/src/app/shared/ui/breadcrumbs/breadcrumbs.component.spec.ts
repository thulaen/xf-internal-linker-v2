import { ComponentFixture, TestBed } from '@angular/core/testing';
import { BreadcrumbsComponent } from './breadcrumbs.component';
import { BreadcrumbService } from '../../../core/services/breadcrumb.service';
import { signal } from '@angular/core';
import { By } from '@angular/platform-browser';
import { RouterTestingModule } from '@angular/router/testing';
import { MatIconModule } from '@angular/material/icon';

describe('BreadcrumbsComponent', () => {
  let fixture: ComponentFixture<BreadcrumbsComponent>;
  let mockSvc: {
    visible: ReturnType<typeof signal<boolean>>;
    crumbs: ReturnType<typeof signal<Array<{ label: string; url: string; current: boolean }>>>;
  };

  beforeEach(async () => {
    mockSvc = {
      visible: signal(false),
      crumbs: signal([])
    };

    await TestBed.configureTestingModule({
      imports: [BreadcrumbsComponent, RouterTestingModule, MatIconModule],
      providers: [
        { provide: BreadcrumbService, useValue: mockSvc }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(BreadcrumbsComponent);
    fixture.detectChanges();
  });

  it('should not render when not visible', () => {
    mockSvc.visible.set(false);
    fixture.detectChanges();
    const nav = fixture.debugElement.query(By.css('nav'));
    expect(nav).toBeNull();
  });

  it('should render crumbs when visible', () => {
    const testCrumbs = [
      { label: 'Home', url: '/', current: false },
      { label: 'Settings', url: '/settings', current: false },
      { label: 'General', url: '/settings/general', current: true }
    ];
    mockSvc.visible.set(true);
    mockSvc.crumbs.set(testCrumbs);
    fixture.detectChanges();

    const nav = fixture.debugElement.query(By.css('nav'));
    expect(nav).toBeTruthy();

    const items = fixture.debugElement.queryAll(By.css('.bc-item'));
    expect(items.length).toBe(3);

    // First crumb is a link
    const firstLink = items[0].query(By.css('a'));
    expect(firstLink.nativeElement.textContent).toContain('Home');
    expect(firstLink.nativeElement.getAttribute('href')).toBe('/');

    // Last crumb is current (span)
    const currentCrumb = items[2].query(By.css('.bc-current'));
    expect(currentCrumb.nativeElement.textContent).toContain('General');
    expect(currentCrumb.nativeElement.getAttribute('aria-current')).toBe('page');

    // Separators (chevrons) should be present on non-last items
    const seps = fixture.debugElement.queryAll(By.css('.bc-sep'));
    expect(seps.length).toBe(2);
  });
});
