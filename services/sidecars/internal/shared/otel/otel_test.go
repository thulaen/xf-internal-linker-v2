package otel

import (
	"context"
	"io"
	"log/slog"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"
)

// quietLogger sends all log output to io.Discard. The otel server logs from
// a background goroutine; routing that through *testing.T races with
// post-test cleanup. Tests here don't assert on log output, so silencing
// avoids the race without losing coverage.
func quietLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// pickFreeAddr finds an unused localhost port so the test does not race
// with the default 6061.
func pickFreeAddr(t *testing.T) string {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("pick free addr: %v", err)
	}
	addr := l.Addr().String()
	_ = l.Close()
	return addr
}

func TestStart_HealthzReturnsOK(t *testing.T) {
	addr := pickFreeAddr(t)
	s := Start(Options{
		Addr:   addr,
		Logger: quietLogger(),
	})
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = s.Shutdown(ctx)
	}()
	// Wait for the listener to come up.
	if err := waitForHealthz("http://" + addr + "/healthz"); err != nil {
		t.Fatalf("healthz did not come up: %v", err)
	}
}

func TestStart_HealthzReports503OnUnhealthy(t *testing.T) {
	addr := pickFreeAddr(t)
	s := Start(Options{
		Addr:           addr,
		HealthReporter: func() (string, bool) { return "draining", false },
		Logger:         quietLogger(),
	})
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = s.Shutdown(ctx)
	}()
	// Wait for the server, then expect 503.
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		resp, err := http.Get("http://" + addr + "/healthz")
		if err == nil {
			defer func() { _ = resp.Body.Close() }()
			body, _ := io.ReadAll(resp.Body)
			if resp.StatusCode != http.StatusServiceUnavailable {
				t.Fatalf("status: got %d, want 503", resp.StatusCode)
			}
			if !strings.Contains(string(body), "draining") {
				t.Fatalf("body: got %s, want to contain 'draining'", body)
			}
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatal("healthz did not come up")
}

func TestStart_PprofMounted(t *testing.T) {
	addr := pickFreeAddr(t)
	s := Start(Options{
		Addr:   addr,
		Logger: quietLogger(),
	})
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = s.Shutdown(ctx)
	}()
	if err := waitForHealthz("http://" + addr + "/healthz"); err != nil {
		t.Fatalf("server did not start: %v", err)
	}
	// pprof index should respond 200 OK.
	resp, err := http.Get("http://" + addr + "/debug/pprof/")
	if err != nil {
		t.Fatalf("pprof GET: %v", err)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("pprof status: got %d, want 200", resp.StatusCode)
	}
}

func TestStart_SetsCPUProfileRate(t *testing.T) {
	addr := pickFreeAddr(t)
	var gotRate int
	original := setCPUProfileRate
	setCPUProfileRate = func(rate int) {
		gotRate = rate
	}
	defer func() { setCPUProfileRate = original }()

	s := Start(Options{
		Addr:   addr,
		Logger: quietLogger(),
	})
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = s.Shutdown(ctx)
	}()
	if gotRate != CPUProfileRateHz {
		t.Fatalf("CPU profile rate: got %d, want %d", gotRate, CPUProfileRateHz)
	}
	if gotRate != 500 {
		t.Fatalf("CPU profile rate: got %d, want 500", gotRate)
	}
}

func TestShutdown_RespectsContext(t *testing.T) {
	addr := pickFreeAddr(t)
	s := Start(Options{
		Addr:   addr,
		Logger: quietLogger(),
	})
	if err := waitForHealthz("http://" + addr + "/healthz"); err != nil {
		t.Fatalf("server did not start: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := s.Shutdown(ctx); err != nil {
		t.Fatalf("Shutdown: %v", err)
	}
}

func TestAddr_ReturnsBoundAddress(t *testing.T) {
	addr := pickFreeAddr(t)
	s := Start(Options{Addr: addr, Logger: quietLogger()})
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = s.Shutdown(ctx)
	}()
	if got := s.Addr(); got != addr {
		t.Fatalf("Addr: got %q, want %q", got, addr)
	}
}

func waitForHealthz(url string) error {
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		resp, err := http.Get(url)
		if err == nil {
			defer func() { _ = resp.Body.Close() }()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		time.Sleep(20 * time.Millisecond)
	}
	return errHealthzTimeout
}

var errHealthzTimeout = &healthzErr{msg: "healthz did not become ready"}

type healthzErr struct{ msg string }

func (e *healthzErr) Error() string { return e.msg }
