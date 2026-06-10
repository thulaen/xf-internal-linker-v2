// Package pool provides shared sync.Pool buffer reuse across the 40 sidecar
// services. Three pools cover the typical request sizes:
//
//	Small  — 1 KiB  (RPC headers, small metadata blobs)
//	Medium — 8 KiB  (typical payloads)
//	Large  — 64 KiB (max single-row Parquet record for snapshotd)
//
// The buffer cap from docs/specs/fr-sidecars-host.md is 64 KiB per snapshot
// row; anything larger is rejected by snapshotd's input validator so the
// pool ceiling matches.
//
// Allocations larger than 64 KiB bypass the pool and use the heap directly —
// they are rare and the pool would just churn memory chasing them.
//
// Reference: https://pkg.go.dev/sync#Pool ; Donovan & Kernighan 2015 §9.
package pool

import "sync"

const (
	SmallBufferSize  = 1 << 10  // 1 KiB
	MediumBufferSize = 8 << 10  // 8 KiB
	LargeBufferSize  = 64 << 10 // 64 KiB
)

// Buffer is a fixed-capacity byte slice borrowed from the pool. Always call
// Release when done so the underlying array can be reused.
type Buffer struct {
	Bytes []byte
	pool  *sync.Pool
}

// Release returns the buffer to its pool. After Release, the caller must not
// touch Bytes — another goroutine may already have it.
func (b *Buffer) Release() {
	if b == nil || b.pool == nil {
		return
	}
	// Zero out before returning to avoid leaking previous payloads.
	for i := range b.Bytes {
		b.Bytes[i] = 0
	}
	raw := b.Bytes[:0]
	b.pool.Put(&raw)
	b.Bytes = nil
	b.pool = nil
}

// Pools holds the three shared pools. A single Pools instance is created once
// in cmd/sidecars/main.go and passed to every service that wants buffer reuse.
type Pools struct {
	small  *sync.Pool
	medium *sync.Pool
	large  *sync.Pool
}

// New builds the three pools.
func New() *Pools {
	return &Pools{
		small:  newBufferPool(SmallBufferSize),
		medium: newBufferPool(MediumBufferSize),
		large:  newBufferPool(LargeBufferSize),
	}
}

func newBufferPool(size int) *sync.Pool {
	return &sync.Pool{
		New: func() any {
			b := make([]byte, 0, size)
			return &b
		},
	}
}

// Get returns a buffer with capacity at least minCap. Sizes that exceed
// LargeBufferSize bypass the pool and allocate directly — the caller still
// gets a Buffer back so Release works uniformly.
func (p *Pools) Get(minCap int) *Buffer {
	switch {
	case minCap <= SmallBufferSize:
		rawPtr, _ := p.small.Get().(*[]byte)
		raw := *rawPtr
		return &Buffer{Bytes: raw[:0], pool: p.small}
	case minCap <= MediumBufferSize:
		rawPtr, _ := p.medium.Get().(*[]byte)
		raw := *rawPtr
		return &Buffer{Bytes: raw[:0], pool: p.medium}
	case minCap <= LargeBufferSize:
		rawPtr, _ := p.large.Get().(*[]byte)
		raw := *rawPtr
		return &Buffer{Bytes: raw[:0], pool: p.large}
	default:
		// Oversize allocations skip the pool to avoid memory churn.
		return &Buffer{Bytes: make([]byte, 0, minCap)}
	}
}
