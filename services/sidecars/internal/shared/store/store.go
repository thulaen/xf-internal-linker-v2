// Package store hands out a scoped bbolt.DB handle per sidecar service.
//
// Each service stores its files under <RootDir>/<serviceName>/. The default
// database file is <RootDir>/<serviceName>/state.db. Services with their own
// file formats (e.g., snapshotd's Parquet files) can also create files under
// the same directory.
//
// The factory caches open handles so successive Open calls return the same
// *bbolt.DB. Call Close() once at shutdown to release all handles.
//
// References:
//   - https://pkg.go.dev/go.etcd.io/bbolt
//   - docs/specs/fr-sidecars-host.md (per-service storage isolation)
package store

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"go.etcd.io/bbolt"
)

const (
	defaultBoltTimeout = 1 * time.Second
	defaultFileMode    = 0o600
	defaultDirMode     = 0o755
)

// Options is the constructor input.
type Options struct {
	RootDir     string
	BoltTimeout time.Duration
}

// Factory hands out scoped bbolt.DB handles.
type Factory struct {
	rootDir     string
	boltTimeout time.Duration

	mu   sync.Mutex
	open map[string]*bbolt.DB
}

// New builds a Factory. RootDir must be non-empty.
func New(opts Options) (*Factory, error) {
	if opts.RootDir == "" {
		return nil, errors.New("store: RootDir is required")
	}
	if opts.BoltTimeout <= 0 {
		opts.BoltTimeout = defaultBoltTimeout
	}
	if err := os.MkdirAll(opts.RootDir, defaultDirMode); err != nil {
		return nil, fmt.Errorf("create root dir %q: %w", opts.RootDir, err)
	}
	return &Factory{
		rootDir:     opts.RootDir,
		boltTimeout: opts.BoltTimeout,
		open:        make(map[string]*bbolt.DB),
	}, nil
}

// For returns the bbolt.DB scoped to the named service. Successive calls with
// the same name return the same handle.
func (f *Factory) For(serviceName string) (*bbolt.DB, error) {
	if serviceName == "" {
		return nil, errors.New("store: serviceName is required")
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	if db, ok := f.open[serviceName]; ok {
		return db, nil
	}
	dir := f.DirFor(serviceName)
	if err := os.MkdirAll(dir, defaultDirMode); err != nil {
		return nil, fmt.Errorf("create service dir %q: %w", dir, err)
	}
	dbPath := filepath.Join(dir, "state.db")
	db, err := bbolt.Open(dbPath, defaultFileMode, &bbolt.Options{Timeout: f.boltTimeout})
	if err != nil {
		return nil, fmt.Errorf("bolt open %q: %w", dbPath, err)
	}
	f.open[serviceName] = db
	return db, nil
}

// DirFor returns the absolute directory the named service may use for its
// own files (Parquet, Bolt, anything). Created lazily by For() but exposed
// so services can write extra files without re-implementing the path scheme.
func (f *Factory) DirFor(serviceName string) string {
	return filepath.Join(f.rootDir, serviceName)
}

// Close closes every cached handle. Errors are joined; closing continues
// even when one handle fails.
func (f *Factory) Close() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	var errs []error
	for name, db := range f.open {
		if err := db.Close(); err != nil {
			errs = append(errs, fmt.Errorf("close %s: %w", name, err))
		}
	}
	f.open = make(map[string]*bbolt.DB)
	return errors.Join(errs...)
}
