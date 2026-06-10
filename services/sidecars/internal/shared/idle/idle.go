// Package idle tracks per-service activity and releases caches on
// inactivity or memory pressure.
//
// Each of the 40 internal sidecar services registers itself with the
// Tracker. Every RPC handler calls Touch(name) so the tracker knows the
// service is live. A background goroutine polls and calls Idle() on
// services that have been silent for IdleAfter (default 30 s).
//
// When the budget package signals memory pressure, ForceReleaseLowest is
// invoked: the tracker picks the lowest-priority service that has not been
// idled in the last MinBetweenReleases and calls Idle() on it. Priority is
// declared in services.manifest.yaml.
//
// References:
//   - docs/specs/fr-sidecars-host.md (budget enforcement)
//   - Donovan & Kernighan 2015 §8 (channels + tickers)
package idle

import (
	"context"
	"log/slog"
	"sort"
	"sync"
	"time"
)

const (
	defaultIdleAfter          = 30 * time.Second
	defaultPollInterval       = 5 * time.Second
	defaultMinBetweenReleases = 5 * time.Second
)

// Priority orders services for forced release under memory pressure.
// PriorityLow services release first; PriorityHigh release last.
type Priority int

const (
	PriorityLow Priority = iota
	PriorityMedium
	PriorityHigh
)

// Idler is the contract every sidecar service implements so it can be
// told to drop in-memory caches.
type Idler interface {
	Idle()
}

// Options is the constructor input.
type Options struct {
	IdleAfter          time.Duration
	PollInterval       time.Duration
	MinBetweenReleases time.Duration
	Logger             *slog.Logger
	Now                func() time.Time
}

type tracked struct {
	name        string
	idler       Idler
	priority    Priority
	lastTouch   time.Time
	lastRelease time.Time
}

// Tracker is the registry + monitor.
type Tracker struct {
	idleAfter          time.Duration
	pollInterval       time.Duration
	minBetweenReleases time.Duration
	logger             *slog.Logger
	now                func() time.Time

	mu       sync.Mutex
	services map[string]*tracked
}

// New builds a Tracker.
func New(opts Options) *Tracker {
	if opts.IdleAfter <= 0 {
		opts.IdleAfter = defaultIdleAfter
	}
	if opts.PollInterval <= 0 {
		opts.PollInterval = defaultPollInterval
	}
	if opts.MinBetweenReleases <= 0 {
		opts.MinBetweenReleases = defaultMinBetweenReleases
	}
	if opts.Logger == nil {
		opts.Logger = slog.Default()
	}
	if opts.Now == nil {
		opts.Now = time.Now
	}
	return &Tracker{
		idleAfter:          opts.IdleAfter,
		pollInterval:       opts.PollInterval,
		minBetweenReleases: opts.MinBetweenReleases,
		logger:             opts.Logger,
		now:                opts.Now,
		services:           make(map[string]*tracked),
	}
}

// Register adds a service to the tracker.
func (t *Tracker) Register(name string, idler Idler, priority Priority) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.services[name] = &tracked{
		name:      name,
		idler:     idler,
		priority:  priority,
		lastTouch: t.now(),
	}
}

// Touch records an RPC for the given service. Called by gRPC interceptors.
func (t *Tracker) Touch(name string) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if s, ok := t.services[name]; ok {
		s.lastTouch = t.now()
	}
}

// Start runs the idle-detection loop until ctx is cancelled.
func (t *Tracker) Start(ctx context.Context) {
	go t.loop(ctx)
}

func (t *Tracker) loop(ctx context.Context) {
	ticker := time.NewTicker(t.pollInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			t.SweepIdle()
		}
	}
}

// SweepIdle releases every service whose last-touch is older than IdleAfter.
// Public so tests can drive it deterministically.
func (t *Tracker) SweepIdle() {
	cutoff := t.now().Add(-t.idleAfter)
	t.mu.Lock()
	toRelease := make([]*tracked, 0, len(t.services))
	for _, s := range t.services {
		if s.lastTouch.Before(cutoff) && s.lastRelease.Before(s.lastTouch) {
			toRelease = append(toRelease, s)
		}
	}
	for _, s := range toRelease {
		s.lastRelease = t.now()
	}
	t.mu.Unlock()
	for _, s := range toRelease {
		t.logger.Info("idle release", "service", s.name)
		s.idler.Idle()
	}
}

// ForceReleaseLowest is invoked from a memory-pressure callback. It picks the
// lowest-priority service that has not been released in the last
// MinBetweenReleases and tells it to drop caches. Returns the name released,
// or empty string if no eligible service exists.
func (t *Tracker) ForceReleaseLowest() string {
	t.mu.Lock()
	candidates := make([]*tracked, 0, len(t.services))
	now := t.now()
	for _, s := range t.services {
		if now.Sub(s.lastRelease) >= t.minBetweenReleases {
			candidates = append(candidates, s)
		}
	}
	if len(candidates) == 0 {
		t.mu.Unlock()
		return ""
	}
	sort.Slice(candidates, func(i, j int) bool {
		// Lowest priority first; among same priority, longer idle first.
		if candidates[i].priority != candidates[j].priority {
			return candidates[i].priority < candidates[j].priority
		}
		return candidates[i].lastTouch.Before(candidates[j].lastTouch)
	})
	winner := candidates[0]
	winner.lastRelease = now
	t.mu.Unlock()

	t.logger.Warn("forced release on memory pressure",
		"service", winner.name, "priority", winner.priority)
	winner.idler.Idle()
	return winner.name
}
