// Package budget owns the global resource cap for the sidecars host.
//
// Slice 1.6 — exactly one Budget exists per process; cmd/sidecars/main.go
// builds it from services.manifest.yaml + budget.yaml at boot and calls
// Apply() once to set runtime/debug.SetMemoryLimit. The monitor goroutine
// fires OnPressure callbacks (registered by internal/shared/idle) when
// resident memory crosses the threshold so low-priority services can
// release caches without the whole binary being killed.
//
// References:
//   - https://pkg.go.dev/runtime/debug#SetMemoryLimit
//   - Donovan & Kernighan 2015 §8 (Go runtime memory model)
//   - docs/specs/fr-sidecars-host.md (the 7 hard constraints)
package budget

import (
	"context"
	"log/slog"
	"math"
	"runtime"
	"runtime/debug"
	"sync"
	"time"
)

const (
	defaultPressureThreshold   = 0.80
	defaultPollInterval        = 1 * time.Second
	defaultMinBetweenCallbacks = 5 * time.Second
)

// RSSReader returns the current resident-set-size in bytes for the process.
// In production this reads runtime.MemStats; tests inject deterministic values.
type RSSReader func() int64

// DefaultRSSReader uses runtime.MemStats (HeapAlloc + StackInuse). This is
// the Go-runtime view of resident memory; Linux's /proc/self/status reports
// slightly higher numbers because of stacks and unreleased OS-level pages,
// but Go's own number is the one debug.SetMemoryLimit acts on.
func DefaultRSSReader() int64 {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	return safeRSSBytes(m.HeapAlloc, m.StackInuse)
}

func safeRSSBytes(heapAlloc, stackInuse uint64) int64 {
	if heapAlloc > math.MaxInt64 || stackInuse > math.MaxInt64-heapAlloc {
		return math.MaxInt64
	}
	return int64(heapAlloc + stackInuse) // #nosec G115 -- bounded above before converting to signed bytes.
}

// Options is the constructor input. Zero values fall back to safe defaults.
type Options struct {
	TotalMemoryBytes    int64
	PressureThreshold   float64 // 0.0..1.0; 0 → defaultPressureThreshold (0.80)
	MinBetweenCallbacks time.Duration
	PollInterval        time.Duration
	RSSReader           RSSReader    // nil → DefaultRSSReader
	Logger              *slog.Logger // nil → slog.Default()
}

// Budget enforces the global RAM cap and signals pressure to subscribers.
type Budget struct {
	totalMemoryBytes    int64
	pressureThreshold   float64
	minBetweenCallbacks time.Duration
	pollInterval        time.Duration
	rssReader           RSSReader
	logger              *slog.Logger

	mu             sync.Mutex
	callbacks      []func(rssBytes int64)
	lastCallbackAt time.Time
}

// New builds a Budget from Options. It does NOT touch the runtime; call Apply
// to set the memory limit and Start to begin polling.
func New(opts Options) *Budget {
	if opts.PressureThreshold <= 0 {
		opts.PressureThreshold = defaultPressureThreshold
	}
	if opts.MinBetweenCallbacks <= 0 {
		opts.MinBetweenCallbacks = defaultMinBetweenCallbacks
	}
	if opts.PollInterval <= 0 {
		opts.PollInterval = defaultPollInterval
	}
	if opts.RSSReader == nil {
		opts.RSSReader = DefaultRSSReader
	}
	if opts.Logger == nil {
		opts.Logger = slog.Default()
	}
	return &Budget{
		totalMemoryBytes:    opts.TotalMemoryBytes,
		pressureThreshold:   opts.PressureThreshold,
		minBetweenCallbacks: opts.MinBetweenCallbacks,
		pollInterval:        opts.PollInterval,
		rssReader:           opts.RSSReader,
		logger:              opts.Logger,
	}
}

// Apply enables the Go-runtime soft cap so the garbage collector pre-empts
// growth before the OS OOM-kills the container. Called once from main.go.
func (b *Budget) Apply() {
	debug.SetMemoryLimit(b.totalMemoryBytes)
}

// OnPressure registers a callback that fires when RSS crosses the threshold.
// Callbacks run in registration order and share one minBetweenCallbacks
// backoff so they don't thrash under sustained pressure.
func (b *Budget) OnPressure(fn func(rssBytes int64)) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.callbacks = append(b.callbacks, fn)
}

// Start spawns the monitor goroutine. It returns immediately; the goroutine
// exits when ctx is cancelled.
func (b *Budget) Start(ctx context.Context) {
	go b.loop(ctx)
}

func (b *Budget) loop(ctx context.Context) {
	ticker := time.NewTicker(b.pollInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			b.checkOnce()
		}
	}
}

// checkOnce reads current RSS and fires callbacks if over the threshold AND
// enough time has elapsed since the last fire. Returns the RSS reading so
// tests can assert on it.
func (b *Budget) checkOnce() int64 {
	rss := b.rssReader()
	threshold := int64(float64(b.totalMemoryBytes) * b.pressureThreshold)
	if rss < threshold {
		return rss
	}
	b.mu.Lock()
	if time.Since(b.lastCallbackAt) < b.minBetweenCallbacks {
		b.mu.Unlock()
		return rss
	}
	b.lastCallbackAt = time.Now()
	callbacks := append([]func(int64){}, b.callbacks...)
	b.mu.Unlock()

	b.logger.Warn("memory pressure",
		"rss_bytes", rss,
		"threshold_bytes", threshold,
		"callback_count", len(callbacks),
	)
	for _, cb := range callbacks {
		cb(rss)
	}
	return rss
}
