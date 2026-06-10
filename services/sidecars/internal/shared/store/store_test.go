package store

import (
	"path/filepath"
	"testing"

	"go.etcd.io/bbolt"
)

func TestNew_RequiresRootDir(t *testing.T) {
	if _, err := New(Options{}); err == nil {
		t.Fatal("New with empty RootDir should error")
	}
}

func TestFor_CreatesScopedDB(t *testing.T) {
	root := t.TempDir()
	f, err := New(Options{RootDir: root})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	defer func() { _ = f.Close() }()

	db, err := f.For("snapshotd")
	if err != nil {
		t.Fatalf("For: %v", err)
	}
	if db == nil {
		t.Fatal("For returned nil DB")
	}
	wantPath := filepath.Join(root, "snapshotd", "state.db")
	if got := db.Path(); got != wantPath {
		t.Fatalf("db path: got %q, want %q", got, wantPath)
	}
}

func TestFor_SameServiceReturnsSameHandle(t *testing.T) {
	root := t.TempDir()
	f, _ := New(Options{RootDir: root})
	defer func() { _ = f.Close() }()
	db1, _ := f.For("topicd")
	db2, _ := f.For("topicd")
	if db1 != db2 {
		t.Fatal("repeated For calls should reuse the handle")
	}
}

func TestFor_DifferentServicesAreIsolated(t *testing.T) {
	root := t.TempDir()
	f, _ := New(Options{RootDir: root})
	defer func() { _ = f.Close() }()

	a, err := f.For("a")
	if err != nil {
		t.Fatalf("For(a): %v", err)
	}
	b, err := f.For("b")
	if err != nil {
		t.Fatalf("For(b): %v", err)
	}
	if a == b {
		t.Fatal("different services must get different DB handles")
	}
	if a.Path() == b.Path() {
		t.Fatal("different services must store at different paths")
	}
}

func TestFor_RequiresServiceName(t *testing.T) {
	root := t.TempDir()
	f, _ := New(Options{RootDir: root})
	defer func() { _ = f.Close() }()
	if _, err := f.For(""); err == nil {
		t.Fatal("empty service name should error")
	}
}

func TestDirFor_StableAcrossCalls(t *testing.T) {
	f, _ := New(Options{RootDir: "/tmp/sidecars-test"})
	got1 := f.DirFor("snapshotd")
	got2 := f.DirFor("snapshotd")
	if got1 != got2 {
		t.Fatalf("DirFor should be stable; got %q vs %q", got1, got2)
	}
	wantSuffix := filepath.Join("sidecars-test", "snapshotd")
	if filepath.Base(filepath.Dir(got1)) != "sidecars-test" || filepath.Base(got1) != "snapshotd" {
		t.Fatalf("DirFor: got %q, want suffix %q", got1, wantSuffix)
	}
}

func TestClose_ReleasesAllHandles(t *testing.T) {
	root := t.TempDir()
	f, _ := New(Options{RootDir: root})
	for _, name := range []string{"a", "b", "c"} {
		if _, err := f.For(name); err != nil {
			t.Fatalf("For(%s): %v", name, err)
		}
	}
	if err := f.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}
	// After Close, For should reopen cleanly.
	if _, err := f.For("a"); err != nil {
		t.Fatalf("re-For after Close: %v", err)
	}
}

func TestFor_BoltDBIsUsable(t *testing.T) {
	root := t.TempDir()
	f, _ := New(Options{RootDir: root})
	defer func() { _ = f.Close() }()
	db, err := f.For("kv")
	if err != nil {
		t.Fatalf("For: %v", err)
	}
	if err := db.Update(func(tx *bbolt.Tx) error {
		bk, err := tx.CreateBucketIfNotExists([]byte("test"))
		if err != nil {
			return err
		}
		return bk.Put([]byte("k"), []byte("v"))
	}); err != nil {
		t.Fatalf("write: %v", err)
	}
	var got []byte
	if err := db.View(func(tx *bbolt.Tx) error {
		got = append(got, tx.Bucket([]byte("test")).Get([]byte("k"))...)
		return nil
	}); err != nil {
		t.Fatalf("read: %v", err)
	}
	if string(got) != "v" {
		t.Fatalf("read back: got %q, want %q", got, "v")
	}
}
