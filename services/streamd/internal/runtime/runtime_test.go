package runtime

import (
	"testing"
	"time"
)

func TestRuntimeDefaultsToShadowModeAndReportsMetrics(t *testing.T) {
	rt := New()
	if rt.Mode() != ModeShadow {
		t.Fatalf("expected shadow mode, got %s", rt.Mode())
	}
	rt.Record("step-a", 2*time.Millisecond, nil)
	report := rt.AdminReport()
	if report.Mode != ModeShadow || report.Operators["step-a"].Count != 1 {
		t.Fatalf("unexpected admin report: %#v", report)
	}
	rt.Pause()
	if !rt.Paused() {
		t.Fatal("runtime should be paused")
	}
	rt.Resume()
	if rt.Paused() {
		t.Fatal("runtime should be resumed")
	}
}

func TestShadowCheckKeepsFallbackWhenParityOrSpeedFails(t *testing.T) {
	rt := New()
	pass := rt.ShadowCheck("state", "same", "same", 11.0)
	if !pass.LiveReady {
		t.Fatalf("expected live-ready shadow check: %#v", pass)
	}
	fail := rt.ShadowCheck("state", "go", "python", 20.0)
	if fail.LiveReady {
		t.Fatalf("parity mismatch must not be live-ready: %#v", fail)
	}
	slow := rt.ShadowCheck("state", "same", "same", 9.9)
	if slow.LiveReady {
		t.Fatalf("slow path must not be live-ready: %#v", slow)
	}
}
