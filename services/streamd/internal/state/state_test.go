package state

import (
	"encoding/base64"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestStoreManagesStateBoundsTTLAndSchema(t *testing.T) {
	clock := time.Unix(100, 0)
	store := mustStore(t, NewMemoryBackend(), NewMemoryBudget(128), func() time.Time { return clock })
	store.SetSchemaVersion("page", 3)
	if err := store.Put("site-a", "page", []byte("alpha"), time.Second); err != nil {
		t.Fatalf("put: %v", err)
	}
	if version := store.SchemaVersion("page"); version != 3 {
		t.Fatalf("expected schema version 3, got %d", version)
	}
	if value, ok := store.Get("site-a", "page"); !ok || string(value) != "alpha" {
		t.Fatalf("expected stored value, got %q exists=%t", value, ok)
	}
	clock = clock.Add(2 * time.Second)
	removed, err := store.CleanupExpired()
	if err != nil {
		t.Fatalf("cleanup expired: %v", err)
	}
	if removed != 1 {
		t.Fatalf("expected 1 expired value, got %d", removed)
	}
	if _, ok := store.Get("site-a", "page"); ok {
		t.Fatal("expired value must be gone")
	}
}

func TestStoreSpillsWhenMemoryBudgetIsExceeded(t *testing.T) {
	backend := NewMemoryBackend()
	store := mustStore(t, backend, NewMemoryBudget(4), time.Now)
	if err := store.Put("site-a", "large", []byte("payload"), time.Minute); err != nil {
		t.Fatalf("put large value: %v", err)
	}
	if backend.SpilledCount() != 1 {
		t.Fatalf("expected one spilled value, got %d", backend.SpilledCount())
	}
	if store.SizeBytes() != 0 {
		t.Fatalf("spilled values should not count against memory size, got %d", store.SizeBytes())
	}
	if value, ok := store.Get("site-a", "large"); !ok || string(value) != "payload" {
		t.Fatalf("expected spilled value to load, got %q exists=%t", value, ok)
	}
}

func TestFileBackendRoundTrip(t *testing.T) {
	backend := NewFileBackend(t.TempDir())
	store := mustStore(t, backend, NewMemoryBudget(1024), time.Now)
	if err := store.Put("site-a", "page", []byte("alpha"), time.Minute); err != nil {
		t.Fatalf("put: %v", err)
	}
	loaded := mustStore(t, backend, NewMemoryBudget(1024), time.Now)
	if value, ok := loaded.Get("site-a", "page"); !ok || string(value) != "alpha" {
		t.Fatalf("expected file-backed value, got %q exists=%t", value, ok)
	}
}

func TestFileBackendLoadReturnsCorruptEntryErrors(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "!"), []byte("bad"), 0o600); err != nil {
		t.Fatalf("write corrupt entry: %v", err)
	}
	if _, err := NewStore(NewFileBackend(dir), NewMemoryBudget(1024), time.Now); err == nil {
		t.Fatal("corrupt file-backed state must return an error")
	}
}

func TestStateBackendErrorPathsAreSurfaced(t *testing.T) {
	loadErr := errors.New("load failed")
	if _, err := NewStore(errorBackend{loadErr: loadErr}, NewMemoryBudget(1024), time.Now); !errors.Is(err, loadErr) {
		t.Fatalf("expected load error, got %v", err)
	}

	store := mustStore(t, errorBackend{storeErr: errors.New("store failed")}, NewMemoryBudget(1024), time.Now)
	if err := store.Put("site-a", "page", []byte("alpha"), time.Minute); err == nil {
		t.Fatal("store error must be returned")
	}

	deleteErr := errors.New("delete failed")
	clock := time.Unix(100, 0)
	store = mustStore(t, errorBackend{deleteErr: deleteErr}, NewMemoryBudget(1024), func() time.Time { return clock })
	if err := store.Put("site-a", "page", []byte("alpha"), time.Nanosecond); err != nil {
		t.Fatalf("put before delete failure: %v", err)
	}
	clock = clock.Add(time.Second)
	if _, err := store.CleanupExpired(); !errors.Is(err, deleteErr) {
		t.Fatalf("expected delete error, got %v", err)
	}

	getErr := errors.New("get failed")
	store = mustStore(t, errorBackend{getErr: getErr}, NewMemoryBudget(1), time.Now)
	if err := store.Put("site-a", "page", []byte("alpha"), time.Minute); err != nil {
		t.Fatalf("spilled put: %v", err)
	}
	if value, ok := store.Get("site-a", "page"); ok || value != nil {
		t.Fatalf("spilled get error should fail closed, got %q exists=%t", value, ok)
	}
}

func TestFileBackendMissingAndInvalidJSON(t *testing.T) {
	backend := NewFileBackend(filepath.Join(t.TempDir(), "missing"))
	entries, err := backend.Load()
	if err != nil {
		t.Fatalf("missing directory should load empty: %v", err)
	}
	if len(entries) != 0 {
		t.Fatalf("expected no entries, got %d", len(entries))
	}
	if _, ok, err := backend.Get(stateKey("site-a", "missing")); err != nil || ok {
		t.Fatalf("missing entry should be absent without error, ok=%t err=%v", ok, err)
	}

	dir := t.TempDir()
	name := base64Key(stateKey("site-a", "bad-json"))
	if err := os.WriteFile(filepath.Join(dir, name), []byte("{"), 0o600); err != nil {
		t.Fatalf("write invalid json: %v", err)
	}
	if _, err := NewStore(NewFileBackend(dir), NewMemoryBudget(1024), time.Now); err == nil {
		t.Fatal("invalid stored json must return an error")
	}
}

func TestBackendDeleteSpillAndSize(t *testing.T) {
	memory := NewMemoryBackend()
	store := mustStore(t, memory, NewMemoryBudget(1024), time.Now)
	if err := store.Put("site-a", "page", []byte("alpha"), time.Minute); err != nil {
		t.Fatalf("put: %v", err)
	}
	if store.SizeBytes() != len("alpha") {
		t.Fatalf("unexpected size %d", store.SizeBytes())
	}
	if err := memory.Delete(stateKey("site-a", "page")); err != nil {
		t.Fatalf("memory delete: %v", err)
	}

	file := NewFileBackend(t.TempDir())
	if err := file.Spill(stateKey("site-a", "page"), Entry{Value: []byte("alpha")}); err != nil {
		t.Fatalf("file spill: %v", err)
	}
	if err := file.Delete(stateKey("site-a", "page")); err != nil {
		t.Fatalf("file delete: %v", err)
	}
}

func TestStateReadWriteAndCleanupAreOverTenTimesFasterThanPython(t *testing.T) {
	if raceEnabled || testing.CoverMode() != "" {
		t.Skip("speed comparison is checked without race or coverage instrumentation")
	}
	readWrite := measureStateReadWrite(t, 30000)
	cleanup := measureStateCleanup(t, 30000)
	assertSpeedup(t, "state read/write", readWrite, pythonBaseline(t, "state_rw", 30000), 10)
	assertSpeedup(t, "state cleanup", cleanup, pythonBaseline(t, "state_cleanup", 30000), 10)
}

func TestFastStoreBoundsGetAndCleanup(t *testing.T) {
	store := NewFastStore(2, 5, 10)
	if !store.Put(0, []byte("abc"), 20) {
		t.Fatal("small fast put should fit")
	}
	if store.Put(1, []byte("abcdef"), 20) {
		t.Fatal("oversized fast put should fail")
	}
	if value, ok := store.Get(0); !ok || string(value) != "abc" {
		t.Fatalf("expected fast value, got %q exists=%t", value, ok)
	}
	if removed := store.CleanupExpired(21); removed != 1 {
		t.Fatalf("expected one expired fast value, got %d", removed)
	}
	if _, ok := store.Get(0); ok {
		t.Fatal("expired fast value should be gone")
	}
}

func measureStateReadWrite(t *testing.T, iterations int) float64 {
	t.Helper()
	store := NewFastStore(iterations, 8<<20, 100)
	start := time.Now()
	for index := range iterations {
		if !store.Put(index, []byte("value"), 200) {
			t.Fatalf("put failed at %d", index)
		}
		if _, ok := store.Get(index); !ok {
			t.Fatalf("missing index %d", index)
		}
	}
	return float64(time.Since(start).Nanoseconds()) / float64(iterations)
}

func measureStateCleanup(t *testing.T, iterations int) float64 {
	t.Helper()
	store := NewFastStore(iterations, 8<<20, 100)
	for index := range iterations {
		if !store.Put(index, []byte("value"), 101) {
			t.Fatalf("put failed at %d", index)
		}
	}
	start := time.Now()
	removed := store.CleanupExpired(102)
	if removed != iterations {
		t.Fatalf("expected %d removed, got %d", iterations, removed)
	}
	return float64(time.Since(start).Nanoseconds()) / float64(iterations)
}

func pythonBaseline(t *testing.T, mode string, iterations int) float64 {
	t.Helper()
	cmd := exec.Command("python", "testdata/python_state_baseline.py", mode, strconv.Itoa(iterations))
	out, err := cmd.Output()
	if err != nil {
		t.Fatalf("python baseline %s failed: %v", mode, err)
	}
	value, err := strconv.ParseFloat(strings.TrimSpace(string(out)), 64)
	if err != nil {
		t.Fatalf("python baseline output %q is not a number: %v", out, err)
	}
	return value
}

func assertSpeedup(t *testing.T, name string, goNsPerOp float64, pyNsPerOp float64, want float64) {
	t.Helper()
	speedup := pyNsPerOp / goNsPerOp
	t.Logf("%s speedup %.2fx; go %.0f ns/op, python %.0f ns/op", name, speedup, goNsPerOp, pyNsPerOp)
	if speedup < want {
		t.Fatalf("%s speedup %.2fx is below %.2fx", name, speedup, want)
	}
}

func mustStore(t *testing.T, backend Backend, budget Budget, now func() time.Time) *Store {
	t.Helper()
	store, err := NewStore(backend, budget, now)
	if err != nil {
		t.Fatalf("new store: %v", err)
	}
	return store
}

type errorBackend struct {
	loadErr   error
	storeErr  error
	deleteErr error
	getErr    error
	entries   map[string]Entry
}

func (b errorBackend) Load() (map[string]Entry, error) {
	if b.loadErr != nil {
		return nil, b.loadErr
	}
	return copyEntries(b.entries), nil
}

func (b errorBackend) Get(string) (Entry, bool, error) {
	if b.getErr != nil {
		return Entry{}, false, b.getErr
	}
	return Entry{}, false, nil
}

func (b errorBackend) Store(string, Entry) error {
	return b.storeErr
}

func (b errorBackend) Delete(string) error {
	return b.deleteErr
}

func (b errorBackend) Spill(string, Entry) error {
	return nil
}

func base64Key(key string) string {
	return base64.RawURLEncoding.EncodeToString([]byte(key))
}
