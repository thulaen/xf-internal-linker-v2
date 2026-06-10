package pruner

import (
	"context"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type testWriter struct{ t *testing.T }

func (w testWriter) Write(p []byte) (int, error) {
	w.t.Logf("%s", p)
	return len(p), nil
}

func testLogger(t *testing.T) *slog.Logger {
	t.Helper()
	return slog.New(slog.NewTextHandler(testWriter{t}, nil))
}

// writeFile creates a fixture file with the given size and modification time.
// The size is exact bytes; the mtime is exact wall-clock so the pruner sees
// the age the test wants.
func writeFile(t *testing.T, path string, sizeBytes int, mtime time.Time) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	body := strings.Repeat("x", sizeBytes)
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	if err := os.Chtimes(path, mtime, mtime); err != nil {
		t.Fatalf("chtimes: %v", err)
	}
}

func countFiles(t *testing.T, root string) int {
	t.Helper()
	n := 0
	_ = filepath.WalkDir(root, func(_ string, d os.DirEntry, _ error) error {
		if d != nil && !d.IsDir() {
			n++
		}
		return nil
	})
	return n
}

func TestRunOnce_DeletesUnpinnedOverAgeLimit(t *testing.T) {
	root := t.TempDir()
	now := time.Now()
	writeFile(t, filepath.Join(root, "fresh.dat"), 1024, now.Add(-1*time.Hour))
	writeFile(t, filepath.Join(root, "stale.dat"), 1024, now.Add(-200*time.Hour)) // 8.3 days

	p := New(Options{
		RootDir:       root,
		TotalCapBytes: 10 << 20, // plenty of headroom
		AgeLimit:      168 * time.Hour,
		Now:           func() time.Time { return now },
		Logger:        testLogger(t),
	})
	if err := p.RunOnce(); err != nil {
		t.Fatalf("RunOnce: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, "stale.dat")); !os.IsNotExist(err) {
		t.Fatal("stale.dat should be deleted by age sweep")
	}
	if _, err := os.Stat(filepath.Join(root, "fresh.dat")); err != nil {
		t.Fatal("fresh.dat should survive age sweep")
	}
}

func TestRunOnce_AgeSweep_SparesPinned(t *testing.T) {
	root := t.TempDir()
	now := time.Now()
	stalePinned := filepath.Join(root, "stale-pinned.dat")
	writeFile(t, stalePinned, 1024, now.Add(-200*time.Hour))

	p := New(Options{
		RootDir:       root,
		TotalCapBytes: 10 << 20,
		AgeLimit:      168 * time.Hour,
		PinChecker:    func(path string) bool { return strings.HasSuffix(path, "stale-pinned.dat") },
		Now:           func() time.Time { return now },
		Logger:        testLogger(t),
	})
	if err := p.RunOnce(); err != nil {
		t.Fatalf("RunOnce: %v", err)
	}
	if _, err := os.Stat(stalePinned); err != nil {
		t.Fatal("pinned stale file should survive age sweep")
	}
}

func TestRunOnce_CapEviction_OldestUnpinnedFirst(t *testing.T) {
	root := t.TempDir()
	now := time.Now()
	// 3 fresh files, 1 KiB each. Cap = 2 KiB so one must go.
	writeFile(t, filepath.Join(root, "a.dat"), 1024, now.Add(-3*time.Hour))
	writeFile(t, filepath.Join(root, "b.dat"), 1024, now.Add(-2*time.Hour))
	writeFile(t, filepath.Join(root, "c.dat"), 1024, now.Add(-1*time.Hour))

	p := New(Options{
		RootDir:       root,
		TotalCapBytes: 2 * 1024,
		AgeLimit:      168 * time.Hour,
		Now:           func() time.Time { return now },
		Logger:        testLogger(t),
	})
	if err := p.RunOnce(); err != nil {
		t.Fatalf("RunOnce: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, "a.dat")); !os.IsNotExist(err) {
		t.Fatal("oldest (a.dat) should be evicted first under cap pressure")
	}
	if _, err := os.Stat(filepath.Join(root, "b.dat")); err != nil {
		t.Fatal("b.dat should survive — cap held after one eviction")
	}
	if _, err := os.Stat(filepath.Join(root, "c.dat")); err != nil {
		t.Fatal("c.dat should survive")
	}
}

func TestRunOnce_CapEviction_PrefersUnpinnedEvenIfPinnedAreOlder(t *testing.T) {
	root := t.TempDir()
	now := time.Now()
	pinnedPath := filepath.Join(root, "pinned-old.dat")
	unpinnedPath := filepath.Join(root, "unpinned-new.dat")
	writeFile(t, pinnedPath, 1024, now.Add(-5*time.Hour))   // older
	writeFile(t, unpinnedPath, 1024, now.Add(-1*time.Hour)) // newer

	p := New(Options{
		RootDir:       root,
		TotalCapBytes: 1024,
		AgeLimit:      168 * time.Hour,
		PinChecker:    func(path string) bool { return strings.HasSuffix(path, "pinned-old.dat") },
		Now:           func() time.Time { return now },
		Logger:        testLogger(t),
	})
	if err := p.RunOnce(); err != nil {
		t.Fatalf("RunOnce: %v", err)
	}
	if _, err := os.Stat(unpinnedPath); !os.IsNotExist(err) {
		t.Fatal("unpinned should be evicted first even if pinned is older")
	}
	if _, err := os.Stat(pinnedPath); err != nil {
		t.Fatal("pinned should survive when an unpinned is available to evict")
	}
}

func TestRunOnce_CapEviction_FallsBackToPinnedLRU(t *testing.T) {
	root := t.TempDir()
	now := time.Now()
	// All files pinned. Cap = 1 KiB, total = 2 KiB. Oldest pinned must go.
	oldPinned := filepath.Join(root, "old-pinned.dat")
	newPinned := filepath.Join(root, "new-pinned.dat")
	writeFile(t, oldPinned, 1024, now.Add(-5*time.Hour))
	writeFile(t, newPinned, 1024, now.Add(-1*time.Hour))

	p := New(Options{
		RootDir:       root,
		TotalCapBytes: 1024,
		AgeLimit:      168 * time.Hour,
		PinChecker:    func(string) bool { return true },
		Now:           func() time.Time { return now },
		Logger:        testLogger(t),
	})
	if err := p.RunOnce(); err != nil {
		t.Fatalf("RunOnce: %v", err)
	}
	if _, err := os.Stat(oldPinned); !os.IsNotExist(err) {
		t.Fatal("oldest pinned must evict when only pinned files remain over cap")
	}
	if _, err := os.Stat(newPinned); err != nil {
		t.Fatal("newer pinned should survive")
	}
}

func TestRunOnce_NoRootDir_IsNoError(t *testing.T) {
	p := New(Options{
		RootDir:       filepath.Join(t.TempDir(), "does-not-exist"),
		TotalCapBytes: 1024,
		Logger:        testLogger(t),
	})
	if err := p.RunOnce(); err != nil {
		t.Fatalf("missing root dir should be a no-op, got %v", err)
	}
}

func TestStart_LoopRespectsContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	root := t.TempDir()
	p := New(Options{
		RootDir:       root,
		TotalCapBytes: 1024,
		Interval:      100 * time.Microsecond,
		Logger:        testLogger(t),
	})
	done := make(chan struct{})
	go func() { p.loop(ctx); close(done) }()
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("pruner loop did not exit on ctx cancel")
	}
}

func TestRunOnce_TerminatesWhenUnderCap(t *testing.T) {
	root := t.TempDir()
	now := time.Now()
	writeFile(t, filepath.Join(root, "a.dat"), 100, now.Add(-1*time.Hour))
	p := New(Options{
		RootDir:       root,
		TotalCapBytes: 10 << 20,
		AgeLimit:      168 * time.Hour,
		Now:           func() time.Time { return now },
		Logger:        testLogger(t),
	})
	if err := p.RunOnce(); err != nil {
		t.Fatalf("RunOnce: %v", err)
	}
	if got := countFiles(t, root); got != 1 {
		t.Fatalf("under cap: expected 1 file to remain, got %d", got)
	}
}
