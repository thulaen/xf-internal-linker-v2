package idle

import (
	"context"
	"log/slog"
	"sync/atomic"
	"testing"
	"time"
)

type testWriter struct{ t *testing.T }

func (w testWriter) Write(p []byte) (int, error) {
	w.t.Logf("%s", p)
	return len(p), nil
}

func testLogger(t *testing.T) *slog.Logger {
	return slog.New(slog.NewTextHandler(testWriter{t}, nil))
}

// fakeIdler records how many times Idle() was called.
type fakeIdler struct{ calls atomic.Int32 }

func (f *fakeIdler) Idle() { f.calls.Add(1) }

func TestSweepIdle_ReleasesAfterIdleAfter(t *testing.T) {
	now := time.Now()
	clock := now
	tr := New(Options{
		IdleAfter: 30 * time.Second,
		Now:       func() time.Time { return clock },
		Logger:    testLogger(t),
	})
	idler := &fakeIdler{}
	tr.Register("topicd", idler, PriorityHigh)

	// 31 s later: should be over IdleAfter, gets released.
	clock = now.Add(31 * time.Second)
	tr.SweepIdle()
	if idler.calls.Load() != 1 {
		t.Fatalf("expected 1 idle call, got %d", idler.calls.Load())
	}
	// Another sweep without a Touch should NOT re-release (lastRelease > lastTouch).
	clock = now.Add(60 * time.Second)
	tr.SweepIdle()
	if idler.calls.Load() != 1 {
		t.Fatalf("expected still 1 idle call after second sweep, got %d", idler.calls.Load())
	}
}

func TestSweepIdle_TouchResetsCounter(t *testing.T) {
	now := time.Now()
	clock := now
	tr := New(Options{
		IdleAfter: 30 * time.Second,
		Now:       func() time.Time { return clock },
		Logger:    testLogger(t),
	})
	idler := &fakeIdler{}
	tr.Register("topicd", idler, PriorityHigh)

	// At 20 s, Touch — counter resets.
	clock = now.Add(20 * time.Second)
	tr.Touch("topicd")
	// At 45 s (25 s after touch), still under IdleAfter.
	clock = now.Add(45 * time.Second)
	tr.SweepIdle()
	if idler.calls.Load() != 0 {
		t.Fatalf("Touch should reset idle counter, got %d calls", idler.calls.Load())
	}
	// At 55 s (35 s after touch), over IdleAfter.
	clock = now.Add(55 * time.Second)
	tr.SweepIdle()
	if idler.calls.Load() != 1 {
		t.Fatalf("expected 1 idle call after touch + idle, got %d", idler.calls.Load())
	}
}

func TestForceReleaseLowest_PicksLowestPriority(t *testing.T) {
	now := time.Now()
	clock := now
	tr := New(Options{
		IdleAfter:          30 * time.Second,
		MinBetweenReleases: 100 * time.Millisecond,
		Now:                func() time.Time { return clock },
		Logger:             testLogger(t),
	})
	high := &fakeIdler{}
	medium := &fakeIdler{}
	low := &fakeIdler{}
	tr.Register("snapshotd", high, PriorityHigh)
	tr.Register("schemard", medium, PriorityMedium)
	tr.Register("anomalyd", low, PriorityLow)

	clock = now.Add(time.Second)
	winner := tr.ForceReleaseLowest()
	if winner != "anomalyd" {
		t.Fatalf("expected lowest-priority service to release, got %q", winner)
	}
	if low.calls.Load() != 1 {
		t.Fatalf("low service should be released once")
	}
	if high.calls.Load() != 0 || medium.calls.Load() != 0 {
		t.Fatalf("only the lowest priority should release")
	}
}

func TestForceReleaseLowest_HonorsBackoff(t *testing.T) {
	now := time.Now()
	clock := now
	tr := New(Options{
		IdleAfter:          30 * time.Second,
		MinBetweenReleases: 200 * time.Millisecond,
		Now:                func() time.Time { return clock },
		Logger:             testLogger(t),
	})
	a := &fakeIdler{}
	tr.Register("anomalyd", a, PriorityLow)

	clock = now.Add(time.Second)
	tr.ForceReleaseLowest() // releases a
	w2 := tr.ForceReleaseLowest()
	if w2 != "" {
		t.Fatalf("backoff should yield empty winner, got %q", w2)
	}
	// After backoff window, can release again.
	clock = now.Add(time.Second + 300*time.Millisecond)
	w3 := tr.ForceReleaseLowest()
	if w3 != "anomalyd" {
		t.Fatalf("after backoff, expected anomalyd, got %q", w3)
	}
}

func TestForceReleaseLowest_SamePriority_PicksLongerIdle(t *testing.T) {
	now := time.Now()
	clock := now
	tr := New(Options{
		IdleAfter:          30 * time.Second,
		MinBetweenReleases: 10 * time.Millisecond,
		Now:                func() time.Time { return clock },
		Logger:             testLogger(t),
	})
	a := &fakeIdler{}
	b := &fakeIdler{}
	tr.Register("a", a, PriorityLow)
	clock = now.Add(5 * time.Second)
	tr.Register("b", b, PriorityLow) // newer touch
	clock = now.Add(10 * time.Second)
	winner := tr.ForceReleaseLowest()
	if winner != "a" {
		t.Fatalf("among same priority, longer-idle should release; got %q", winner)
	}
}

func TestStart_LoopRespectsContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	tr := New(Options{
		PollInterval: 100 * time.Microsecond,
		Logger:       testLogger(t),
	})
	done := make(chan struct{})
	go func() { tr.loop(ctx); close(done) }()
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("idle loop did not exit on ctx cancel")
	}
}
