package budget

import (
	"context"
	"log/slog"
	"math"
	"sync/atomic"
	"testing"
	"time"
)

// testWriter routes slog output to t.Logf so failing tests show what the
// monitor logged. Stays silent on passes.
type testWriter struct{ t *testing.T }

func (w testWriter) Write(p []byte) (int, error) {
	w.t.Logf("%s", p)
	return len(p), nil
}

func testLogger(t *testing.T) *slog.Logger {
	t.Helper()
	return slog.New(slog.NewTextHandler(testWriter{t}, nil))
}

func TestNew_DefaultsApplied(t *testing.T) {
	b := New(Options{TotalMemoryBytes: 512 << 20})
	if b.pressureThreshold != defaultPressureThreshold {
		t.Fatalf("pressure threshold: got %v, want %v", b.pressureThreshold, defaultPressureThreshold)
	}
	if b.minBetweenCallbacks != defaultMinBetweenCallbacks {
		t.Fatalf("min between callbacks: got %v, want %v", b.minBetweenCallbacks, defaultMinBetweenCallbacks)
	}
	if b.pollInterval != defaultPollInterval {
		t.Fatalf("poll interval: got %v, want %v", b.pollInterval, defaultPollInterval)
	}
	if b.rssReader == nil {
		t.Fatal("rss reader must not be nil after New")
	}
	if b.logger == nil {
		t.Fatal("logger must not be nil after New")
	}
}

func TestCheckOnce_BelowThreshold_DoesNotFire(t *testing.T) {
	fired := false
	b := New(Options{
		TotalMemoryBytes:    100 << 20,
		PressureThreshold:   0.80,
		MinBetweenCallbacks: time.Microsecond,
		RSSReader:           func() int64 { return 50 << 20 }, // 50 MB, below 80 MB threshold
		Logger:              testLogger(t),
	})
	b.OnPressure(func(int64) { fired = true })
	rss := b.checkOnce()
	if rss != 50<<20 {
		t.Fatalf("rss: got %d, want %d", rss, 50<<20)
	}
	if fired {
		t.Fatal("callback fired below threshold")
	}
}

func TestCheckOnce_AboveThreshold_FiresOnce(t *testing.T) {
	var rssBytes atomic.Int64
	rssBytes.Store(50 << 20)
	fired := make(chan int64, 1)
	b := New(Options{
		TotalMemoryBytes:    100 << 20,
		PressureThreshold:   0.50,
		MinBetweenCallbacks: time.Microsecond,
		RSSReader:           func() int64 { return rssBytes.Load() },
		Logger:              testLogger(t),
	})
	b.OnPressure(func(rss int64) {
		select {
		case fired <- rss:
		default:
		}
	})
	rssBytes.Store(70 << 20) // 70 MB > 50 MB threshold
	got := b.checkOnce()
	if got != 70<<20 {
		t.Fatalf("rss: got %d, want %d", got, 70<<20)
	}
	select {
	case <-fired:
	case <-time.After(100 * time.Millisecond):
		t.Fatal("callback did not fire")
	}
}

func TestCheckOnce_BackoffHonored(t *testing.T) {
	var rssBytes atomic.Int64
	rssBytes.Store(90 << 20) // well over threshold
	var fireCount atomic.Int32
	b := New(Options{
		TotalMemoryBytes:    100 << 20,
		PressureThreshold:   0.50,
		MinBetweenCallbacks: 50 * time.Millisecond,
		RSSReader:           func() int64 { return rssBytes.Load() },
		Logger:              testLogger(t),
	})
	b.OnPressure(func(int64) { fireCount.Add(1) })
	b.checkOnce() // fires (1)
	b.checkOnce() // suppressed by backoff
	b.checkOnce() // suppressed by backoff
	if c := fireCount.Load(); c != 1 {
		t.Fatalf("fire count under backoff: got %d, want 1", c)
	}
	time.Sleep(60 * time.Millisecond) // outside backoff window
	b.checkOnce()                     // fires (2)
	if c := fireCount.Load(); c != 2 {
		t.Fatalf("fire count after backoff: got %d, want 2", c)
	}
}

func TestCheckOnce_MultipleCallbacks_AllFire(t *testing.T) {
	var a, b2 atomic.Int32
	b := New(Options{
		TotalMemoryBytes:    100 << 20,
		PressureThreshold:   0.50,
		MinBetweenCallbacks: time.Microsecond,
		RSSReader:           func() int64 { return 90 << 20 },
		Logger:              testLogger(t),
	})
	b.OnPressure(func(int64) { a.Add(1) })
	b.OnPressure(func(int64) { b2.Add(1) })
	b.checkOnce()
	if a.Load() != 1 || b2.Load() != 1 {
		t.Fatalf("both callbacks should fire: a=%d b=%d", a.Load(), b2.Load())
	}
}

func TestStart_LoopRespectsContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	b := New(Options{
		TotalMemoryBytes:  1 << 30,
		PressureThreshold: 0.99,
		PollInterval:      100 * time.Microsecond,
		RSSReader:         func() int64 { return 0 },
		Logger:            testLogger(t),
	})
	done := make(chan struct{})
	go func() {
		b.loop(ctx)
		close(done)
	}()
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("loop did not exit on ctx cancel")
	}
}

func TestDefaultRSSReader_ReturnsPositive(t *testing.T) {
	got := DefaultRSSReader()
	if got <= 0 {
		t.Fatalf("DefaultRSSReader should return > 0 in a running test, got %d", got)
	}
}

func TestSafeRSSBytes_SaturatesOverflow(t *testing.T) {
	got := safeRSSBytes(math.MaxUint64, 1)
	if got != math.MaxInt64 {
		t.Fatalf("safeRSSBytes overflow: got %d, want %d", got, int64(math.MaxInt64))
	}
}

func TestApply_DoesNotPanic(t *testing.T) {
	// debug.SetMemoryLimit accepts any non-zero int64; we don't want to
	// assert side-effects on the test process. Just confirm Apply runs cleanly.
	b := New(Options{TotalMemoryBytes: 512 << 20})
	b.Apply()
	// Restore to a permissive value so other tests in this binary aren't
	// constrained by our 512 MB cap.
	b2 := New(Options{TotalMemoryBytes: 8 << 30})
	b2.Apply()
}
