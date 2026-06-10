// Package pruner walks /var/lib/xf/sidecars/ on a timer and enforces the
// host-level storage budget from services/sidecars/budget.yaml.
//
// Eviction policy (in order):
//
//  1. Unpinned files older than AgeLimit are deleted regardless of cap state.
//  2. If total bytes still exceed TotalCapBytes, sort the remaining unpinned
//     files by mtime ascending and delete oldest-first until under cap.
//  3. If only pinned files remain and total bytes still exceed cap, evict
//     least-recently-touched pinned files (LRU) until under cap. The
//     PinChecker decides which files count as pinned (e.g., snapshotd marks
//     files via its companion meta sidecar; the default checker returns
//     false so the package is usable without any pin signal).
//
// The package does NOT file paper-trail entries directly. When a pinned
// file is evicted, the eviction event is logged at WARN level so the
// surrounding Python layer can emit a paper-trail entry tagged
// snapshotd_overflow.
//
// References:
//   - docs/specs/fr-sidecars-host.md (the 7 hard constraints)
//   - Iceberg manifest spec (pinned-snapshot semantics)
//   - https://pkg.go.dev/io/fs#WalkDirFunc
package pruner

import (
	"context"
	"errors"
	"io/fs"
	"log/slog"
	"os"
	"path/filepath"
	"sort"
	"time"
)

const (
	defaultAgeLimit = 168 * time.Hour // 7 days
	defaultInterval = 60 * time.Second
)

// PinChecker reports whether the file at path is pinned. Pinned files are
// exempt from the age sweep but still count toward the cap.
type PinChecker func(path string) bool

// Options is the constructor input.
type Options struct {
	RootDir       string
	TotalCapBytes int64
	AgeLimit      time.Duration
	Interval      time.Duration
	PinChecker    PinChecker
	Logger        *slog.Logger
	Now           func() time.Time // injectable clock for tests
}

// Pruner walks RootDir on a timer and evicts according to the policy.
type Pruner struct {
	rootDir       string
	totalCapBytes int64
	ageLimit      time.Duration
	interval      time.Duration
	pinChecker    PinChecker
	logger        *slog.Logger
	now           func() time.Time
}

// fileEntry is the unit the pruner sorts on.
type fileEntry struct {
	path     string
	size     int64
	mtime    time.Time
	isPinned bool
}

// New builds a Pruner. Zero values fall back to safe defaults.
func New(opts Options) *Pruner {
	if opts.AgeLimit <= 0 {
		opts.AgeLimit = defaultAgeLimit
	}
	if opts.Interval <= 0 {
		opts.Interval = defaultInterval
	}
	if opts.PinChecker == nil {
		opts.PinChecker = func(string) bool { return false }
	}
	if opts.Logger == nil {
		opts.Logger = slog.Default()
	}
	if opts.Now == nil {
		opts.Now = time.Now
	}
	return &Pruner{
		rootDir:       opts.RootDir,
		totalCapBytes: opts.TotalCapBytes,
		ageLimit:      opts.AgeLimit,
		interval:      opts.Interval,
		pinChecker:    opts.PinChecker,
		logger:        opts.Logger,
		now:           opts.Now,
	}
}

// Start runs the periodic eviction loop until ctx is cancelled.
func (p *Pruner) Start(ctx context.Context) {
	go p.loop(ctx)
}

func (p *Pruner) loop(ctx context.Context) {
	ticker := time.NewTicker(p.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := p.RunOnce(); err != nil {
				p.logger.Warn("pruner sweep failed", "err", err)
			}
		}
	}
}

// RunOnce is one full eviction pass. Public so tests can drive it.
func (p *Pruner) RunOnce() error {
	entries, err := p.scan()
	if err != nil {
		return err
	}
	totalBytes := sumBytes(entries)
	totalBytes = p.sweepAged(entries, totalBytes)
	if totalBytes > p.totalCapBytes {
		// Re-scan since sweepAged may have deleted files.
		entries, err = p.scan()
		if err != nil {
			return err
		}
		totalBytes = sumBytes(entries)
		totalBytes = p.evictUnpinned(entries, totalBytes)
	}
	if totalBytes > p.totalCapBytes {
		entries, err = p.scan()
		if err != nil {
			return err
		}
		totalBytes = sumBytes(entries)
		totalBytes = p.evictPinned(entries, totalBytes)
	}
	if totalBytes > p.totalCapBytes {
		p.logger.Error("pruner could not bring storage under cap",
			"total_bytes", totalBytes, "cap_bytes", p.totalCapBytes)
	}
	return nil
}

func (p *Pruner) scan() ([]fileEntry, error) {
	out := make([]fileEntry, 0, 64)
	err := filepath.WalkDir(p.rootDir, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			if errors.Is(walkErr, fs.ErrNotExist) {
				return nil
			}
			return walkErr
		}
		if d.IsDir() {
			return nil
		}
		info, err := d.Info()
		if err != nil {
			return nil // skip vanished files
		}
		out = append(out, fileEntry{
			path:     path,
			size:     info.Size(),
			mtime:    info.ModTime(),
			isPinned: p.pinChecker(path),
		})
		return nil
	})
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return nil, err
	}
	return out, nil
}

// sweepAged deletes unpinned files older than ageLimit. Pinned files survive
// regardless of age. Returns the new total byte count after deletes.
func (p *Pruner) sweepAged(entries []fileEntry, totalBytes int64) int64 {
	cutoff := p.now().Add(-p.ageLimit)
	for _, e := range entries {
		if e.isPinned || e.mtime.After(cutoff) {
			continue
		}
		if err := os.Remove(e.path); err != nil && !errors.Is(err, fs.ErrNotExist) {
			p.logger.Warn("aged file delete failed", "path", e.path, "err", err)
			continue
		}
		totalBytes -= e.size
		p.logger.Debug("aged eviction", "path", e.path, "size", e.size)
	}
	return totalBytes
}

// evictUnpinned deletes unpinned files oldest-first until total fits the cap.
// Pinned files are untouched in this pass.
func (p *Pruner) evictUnpinned(entries []fileEntry, totalBytes int64) int64 {
	unpinned := filterPinned(entries, false)
	sort.Slice(unpinned, func(i, j int) bool { return unpinned[i].mtime.Before(unpinned[j].mtime) })
	for _, e := range unpinned {
		if totalBytes <= p.totalCapBytes {
			break
		}
		if err := os.Remove(e.path); err != nil && !errors.Is(err, fs.ErrNotExist) {
			p.logger.Warn("cap eviction failed", "path", e.path, "err", err)
			continue
		}
		totalBytes -= e.size
		p.logger.Info("cap eviction", "path", e.path, "size", e.size)
	}
	return totalBytes
}

// evictPinned is the last-resort path. Pinned files are LRU-evicted with a
// WARN-level log so the Python layer can file a paper-trail entry.
func (p *Pruner) evictPinned(entries []fileEntry, totalBytes int64) int64 {
	pinned := filterPinned(entries, true)
	sort.Slice(pinned, func(i, j int) bool { return pinned[i].mtime.Before(pinned[j].mtime) })
	for _, e := range pinned {
		if totalBytes <= p.totalCapBytes {
			break
		}
		if err := os.Remove(e.path); err != nil && !errors.Is(err, fs.ErrNotExist) {
			p.logger.Warn("pinned eviction failed", "path", e.path, "err", err)
			continue
		}
		totalBytes -= e.size
		p.logger.Warn("pinned eviction (cap pressure overrode pin)", "path", e.path, "size", e.size)
	}
	return totalBytes
}

func filterPinned(entries []fileEntry, want bool) []fileEntry {
	out := make([]fileEntry, 0, len(entries))
	for _, e := range entries {
		if e.isPinned == want {
			out = append(out, e)
		}
	}
	return out
}

func sumBytes(entries []fileEntry) int64 {
	var total int64
	for _, e := range entries {
		total += e.size
	}
	return total
}
