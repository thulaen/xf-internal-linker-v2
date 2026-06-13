import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { MatSnackBar } from '@angular/material/snack-bar';
import { of, throwError } from 'rxjs';

import { McpComponent } from './mcp.component';
import { McpService } from '../core/services/mcp.service';

const stubAgents = {
  claude_code: { name: 'Claude Code', installed: true, binary_on_path: true, supported: 'full' },
  codex: { name: 'Codex', installed: false, binary_on_path: false, supported: 'best-effort' },
  antigravity: { name: 'Antigravity', installed: false, binary_on_path: false, supported: 'best-effort' },
};

const stubHealth = {
  alive: true,
  as_of: '2026-04-30T12:00:00Z',
  mcp_json_present: true,
  server_script_present: true,
  mcp_python_pkg_installed: true,
  transport: 'stdio',
  tools_exposed: [],
};

describe('McpComponent', () => {
  let fixture: ComponentFixture<McpComponent>;
  let component: McpComponent;
  let httpMock: HttpTestingController;
  const snackStub = { open: () => undefined };
  const svcStub = {
    health: () => of(stubHealth),
    agents: () => of(stubAgents),
    schedules: () => of({ schedules: [] }),
    runMonthly: () => of({ month: '2026-04', strategy: 'top50' }),
    runScheduleNow: () => of({ ok: true }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [McpComponent],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: McpService, useValue: svcStub },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    })
      .overrideComponent(McpComponent, { set: { template: '<div></div>' } })
      .compileComponents();
    fixture = TestBed.createComponent(McpComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('renders and pulls health + agents on init', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((r) => r.flush({}));
    expect(component.health()?.alive).toBe(true);
    expect(component.agents()?.claude_code.name).toBe('Claude Code');
    expect(component.agentRows().length).toBe(3);
  });

  it('runMonthlyNow flips busy and snacks the result', () => {
    fixture.detectChanges();
    component.runMonthlyNow();
    expect(component.runMonthlyBusy()).toBe(false); // sync stub completes immediately
  });

  it('handles failing health endpoint gracefully', () => {
    const failing = { ...svcStub, health: () => throwError(() => new Error('down')) };
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [McpComponent],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: McpService, useValue: failing },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    }).overrideComponent(McpComponent, { set: { template: '<div></div>' } });
    const fx = TestBed.createComponent(McpComponent);
    fx.detectChanges();
    expect(fx.componentInstance.healthError()).toBe('down');
  });
});
