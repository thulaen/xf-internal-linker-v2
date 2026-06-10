package socket

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestListen_RequiresPath(t *testing.T) {
	if _, err := Listen(""); err == nil {
		t.Fatal("empty path should error")
	}
}

func TestListen_CreatesSocketAtCorrectMode(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("AF_UNIX listen requires a POSIX OS")
	}
	root := t.TempDir()
	path := filepath.Join(root, "sub", "sidecars.sock")
	ln, err := Listen(path)
	if err != nil {
		t.Fatalf("Listen: %v", err)
	}
	defer func() { _ = ln.Close() }()
	defer func() { _ = os.Remove(path) }()

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("stat socket: %v", err)
	}
	// The exact permission bits should be 0660 — read/write for owner and group,
	// no access for others. (sticky/setuid bits are masked out.)
	gotMode := info.Mode().Perm()
	if gotMode != DefaultMode {
		t.Fatalf("socket mode: got %o, want %o", gotMode, DefaultMode)
	}
}

func TestListen_RemovesStaleSocket(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("AF_UNIX listen requires a POSIX OS")
	}
	root := t.TempDir()
	path := filepath.Join(root, "sidecars.sock")
	// Pretend a previous run crashed and left a regular file at the path.
	if err := os.WriteFile(path, []byte("leftover"), 0o644); err != nil {
		t.Fatalf("seed stale: %v", err)
	}
	ln, err := Listen(path)
	if err != nil {
		t.Fatalf("Listen: %v", err)
	}
	defer func() { _ = ln.Close() }()
	defer func() { _ = os.Remove(path) }()
}

func TestEnsureParentDir_CreatesNestedDirs(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "a", "b", "c", "sidecars.sock")
	if err := EnsureParentDir(path); err != nil {
		t.Fatalf("EnsureParentDir: %v", err)
	}
	if _, err := os.Stat(filepath.Dir(path)); err != nil {
		t.Fatalf("parent dir not created: %v", err)
	}
}

func TestRemoveStale_NonexistentIsNotError(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "never-existed.sock")
	if err := RemoveStale(path); err != nil {
		t.Fatalf("RemoveStale: %v", err)
	}
}
