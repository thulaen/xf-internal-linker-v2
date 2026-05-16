package state

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

var ErrBudgetExceeded = errors.New("state memory budget exceeded")

type Budget struct {
	LimitBytes int
}

type Entry struct {
	Value     []byte
	ExpiresAt time.Time
	Spilled   bool
}

type Backend interface {
	Load() (map[string]Entry, error)
	Get(key string) (Entry, bool, error)
	Store(key string, entry Entry) error
	Delete(key string) error
	Spill(key string, entry Entry) error
}

type Store struct {
	mu       sync.RWMutex
	backend  Backend
	budget   Budget
	now      func() time.Time
	entries  map[string]Entry
	schemas  map[string]int
	sizeByte int
}

func NewMemoryBudget(limitBytes int) Budget {
	return Budget{LimitBytes: limitBytes}
}

func NewStore(backend Backend, budget Budget, now func() time.Time) (*Store, error) {
	entries, err := backend.Load()
	if err != nil {
		return nil, err
	}
	return &Store{
		backend:  backend,
		budget:   budget,
		now:      now,
		entries:  entries,
		schemas:  make(map[string]int),
		sizeByte: totalSize(entries),
	}, nil
}

func (s *Store) Put(scope string, key string, value []byte, ttl time.Duration) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	fullKey := stateKey(scope, key)
	entry := Entry{Value: append([]byte(nil), value...), ExpiresAt: s.now().Add(ttl)}
	old := len(s.entries[fullKey].Value)
	nextSize := s.sizeByte - old + len(value)
	if s.budget.LimitBytes > 0 && nextSize > s.budget.LimitBytes {
		entry.Spilled = true
		if err := s.backend.Spill(fullKey, entry); err != nil {
			return err
		}
		s.entries[fullKey] = Entry{ExpiresAt: entry.ExpiresAt, Spilled: true}
		s.sizeByte -= old
		return nil
	} else if err := s.backend.Store(fullKey, entry); err != nil {
		return err
	}
	s.entries[fullKey] = entry
	s.sizeByte = nextSize
	return nil
}

func (s *Store) Get(scope string, key string) ([]byte, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	fullKey := stateKey(scope, key)
	entry, ok := s.entries[fullKey]
	if !ok || !entry.ExpiresAt.After(s.now()) {
		return nil, false
	}
	if entry.Spilled {
		loaded, ok, err := s.backend.Get(fullKey)
		if err != nil || !ok || !loaded.ExpiresAt.After(s.now()) {
			return nil, false
		}
		return append([]byte(nil), loaded.Value...), true
	}
	return append([]byte(nil), entry.Value...), true
}

func (s *Store) CleanupExpired() (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	removed := 0
	now := s.now()
	for key, entry := range s.entries {
		if entry.ExpiresAt.After(now) {
			continue
		}
		delete(s.entries, key)
		s.sizeByte -= len(entry.Value)
		if err := s.backend.Delete(key); err != nil {
			return removed, err
		}
		removed++
	}
	return removed, nil
}

func (s *Store) SetSchemaVersion(name string, version int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.schemas[name] = version
}

func (s *Store) SchemaVersion(name string) int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.schemas[name]
}

func (s *Store) SizeBytes() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.sizeByte
}

func totalSize(entries map[string]Entry) int {
	size := 0
	for _, entry := range entries {
		size += len(entry.Value)
	}
	return size
}

func stateKey(scope string, key string) string {
	return scope + "\x00" + key
}

type MemoryBackend struct {
	mu      sync.RWMutex
	entries map[string]Entry
	spilled int
}

func NewMemoryBackend() *MemoryBackend {
	return &MemoryBackend{entries: make(map[string]Entry)}
}

func (b *MemoryBackend) Load() (map[string]Entry, error) {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return copyEntries(b.entries), nil
}

func (b *MemoryBackend) Get(key string) (Entry, bool, error) {
	b.mu.RLock()
	defer b.mu.RUnlock()
	entry, ok := b.entries[key]
	return copyEntry(entry), ok, nil
}

func (b *MemoryBackend) Store(key string, entry Entry) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.entries[key] = copyEntry(entry)
	return nil
}

func (b *MemoryBackend) Delete(key string) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	delete(b.entries, key)
	return nil
}

func (b *MemoryBackend) Spill(key string, entry Entry) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.entries[key] = copyEntry(entry)
	b.spilled++
	return nil
}

func (b *MemoryBackend) SpilledCount() int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return b.spilled
}

type FileBackend struct {
	dir string
}

func NewFileBackend(dir string) *FileBackend {
	return &FileBackend{dir: dir}
}

func (b *FileBackend) Load() (map[string]Entry, error) {
	files, err := os.ReadDir(b.dir)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return map[string]Entry{}, nil
		}
		return nil, err
	}
	return b.loadFiles(files)
}

func (b *FileBackend) Get(key string) (Entry, bool, error) {
	value, err := os.ReadFile(b.path(key))
	if errors.Is(err, os.ErrNotExist) {
		return Entry{}, false, nil
	}
	if err != nil {
		return Entry{}, false, err
	}
	entry, err := decodeEntry(value)
	if err != nil {
		return Entry{}, false, err
	}
	return entry, true, nil
}

func (b *FileBackend) Store(key string, entry Entry) error {
	if err := os.MkdirAll(b.dir, 0o700); err != nil {
		return err
	}
	encoded, err := encodeEntry(entry)
	if err != nil {
		return err
	}
	return os.WriteFile(b.path(key), encoded, 0o600)
}

func (b *FileBackend) Delete(key string) error {
	if err := os.Remove(b.path(key)); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return nil
}

func (b *FileBackend) Spill(key string, entry Entry) error {
	return b.Store(key, entry)
}

func (b *FileBackend) loadFiles(files []os.DirEntry) (map[string]Entry, error) {
	entries := make(map[string]Entry, len(files))
	for _, file := range files {
		if file.IsDir() {
			continue
		}
		key, err := base64.RawURLEncoding.DecodeString(file.Name())
		if err != nil {
			return nil, fmt.Errorf("decode state key %q: %w", file.Name(), err)
		}
		entry, ok, err := b.Get(string(key))
		if err != nil {
			return nil, fmt.Errorf("load state entry %q: %w", file.Name(), err)
		}
		if !ok {
			return nil, fmt.Errorf("state entry disappeared while loading: %q", file.Name())
		}
		entries[string(key)] = entry
	}
	return entries, nil
}

func (b *FileBackend) path(key string) string {
	name := base64.RawURLEncoding.EncodeToString([]byte(key))
	return filepath.Join(b.dir, name)
}

func copyEntries(entries map[string]Entry) map[string]Entry {
	copied := make(map[string]Entry, len(entries))
	for key, entry := range entries {
		copied[key] = copyEntry(entry)
	}
	return copied
}

func copyEntry(entry Entry) Entry {
	entry.Value = append([]byte(nil), entry.Value...)
	return entry
}

type storedEntry struct {
	Value     []byte `json:"value"`
	ExpiresAt int64  `json:"expires_at"`
	Spilled   bool   `json:"spilled"`
}

func encodeEntry(entry Entry) ([]byte, error) {
	return json.Marshal(storedEntry{
		Value:     entry.Value,
		ExpiresAt: entry.ExpiresAt.UnixNano(),
		Spilled:   entry.Spilled,
	})
}

func decodeEntry(value []byte) (Entry, error) {
	var stored storedEntry
	if err := json.Unmarshal(value, &stored); err != nil {
		return Entry{}, err
	}
	return Entry{
		Value:     append([]byte(nil), stored.Value...),
		ExpiresAt: time.Unix(0, stored.ExpiresAt),
		Spilled:   stored.Spilled,
	}, nil
}

type FastStore struct {
	values  [][]byte
	expiry  []int64
	used    int
	limit   int
	current int64
}

func NewFastStore(capacity int, limitBytes int, now int64) *FastStore {
	return &FastStore{
		values:  make([][]byte, capacity),
		expiry:  make([]int64, capacity),
		limit:   limitBytes,
		current: now,
	}
}

func (s *FastStore) Put(index int, value []byte, expiresAt int64) bool {
	next := s.used - len(s.values[index]) + len(value)
	if s.limit > 0 && next > s.limit {
		return false
	}
	s.values[index] = value
	s.expiry[index] = expiresAt
	s.used = next
	return true
}

func (s *FastStore) Get(index int) ([]byte, bool) {
	if s.expiry[index] <= s.current {
		return nil, false
	}
	return s.values[index], true
}

func (s *FastStore) CleanupExpired(now int64) int {
	removed := 0
	for index, expiresAt := range s.expiry {
		if expiresAt == 0 || expiresAt > now {
			continue
		}
		s.used -= len(s.values[index])
		s.values[index] = nil
		s.expiry[index] = 0
		removed++
	}
	return removed
}
