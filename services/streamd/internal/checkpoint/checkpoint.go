package checkpoint

import (
	"errors"
	"strconv"
	"sync"
	"time"
)

const (
	KindCheckpoint = "checkpoint"
	KindSavepoint  = "savepoint"
)

var (
	ErrSnapshotNotFound = errors.New("snapshot not found")
	ErrStepMissing      = errors.New("snapshot step missing")
)

type Snapshot struct {
	ID        string
	Job       string
	Kind      string
	Steps     map[string]uint64
	Bytes     int
	CreatedAt time.Time
}

type Catalog struct {
	mu        sync.RWMutex
	nextID    uint64
	snapshots []Snapshot
	byID      map[string]Snapshot
}

func NewCatalog() *Catalog {
	return &Catalog{byID: make(map[string]Snapshot)}
}

func (c *Catalog) Checkpoint(job string, steps map[string]uint64, bytes int) Snapshot {
	return c.add(job, KindCheckpoint, steps, bytes)
}

func (c *Catalog) Savepoint(job string, steps map[string]uint64, bytes int) Snapshot {
	return c.add(job, KindSavepoint, steps, bytes)
}

func (c *Catalog) ValidateRestore(job string, snapshotID string, requiredSteps []string) error {
	c.mu.RLock()
	snapshot, ok := c.byID[snapshotID]
	c.mu.RUnlock()
	if !ok || snapshot.Job != job {
		return ErrSnapshotNotFound
	}
	for _, step := range requiredSteps {
		if _, ok := snapshot.Steps[step]; !ok {
			return ErrStepMissing
		}
	}
	return nil
}

func (c *Catalog) List(job string) []Snapshot {
	c.mu.RLock()
	defer c.mu.RUnlock()
	out := make([]Snapshot, 0, len(c.snapshots))
	for _, snapshot := range c.snapshots {
		if snapshot.Job == job {
			out = append(out, copySnapshot(snapshot))
		}
	}
	return out
}

func (c *Catalog) add(job string, kind string, steps map[string]uint64, bytes int) Snapshot {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.nextID++
	snapshot := Snapshot{
		ID:        kind + "-" + strconv.FormatUint(c.nextID, 10),
		Job:       job,
		Kind:      kind,
		Steps:     copySteps(steps),
		Bytes:     bytes,
		CreatedAt: time.Now().UTC(),
	}
	c.snapshots = append(c.snapshots, snapshot)
	c.byID[snapshot.ID] = snapshot
	return copySnapshot(snapshot)
}

func copySnapshot(snapshot Snapshot) Snapshot {
	snapshot.Steps = copySteps(snapshot.Steps)
	return snapshot
}

func copySteps(steps map[string]uint64) map[string]uint64 {
	copied := make(map[string]uint64, len(steps))
	for step, offset := range steps {
		copied[step] = offset
	}
	return copied
}

type FastCatalog struct {
	nextID  uint64
	stepIDs []uint16
	offsets []uint64
	bytes   []int
	steps   []bool
}

func NewFastCatalog(capacity int) *FastCatalog {
	return &FastCatalog{
		stepIDs: make([]uint16, 0, capacity),
		offsets: make([]uint64, 0, capacity),
		bytes:   make([]int, 0, capacity),
		steps:   make([]bool, 65536),
	}
}

func (c *FastCatalog) Record(stepID uint16, offset uint64, bytes int) uint64 {
	c.nextID++
	c.stepIDs = append(c.stepIDs, stepID)
	c.offsets = append(c.offsets, offset)
	c.bytes = append(c.bytes, bytes)
	c.steps[stepID] = true
	return c.nextID
}

func (c *FastCatalog) CanRestore(stepID uint16) bool {
	return c.steps[stepID]
}
