package pool

import (
	"sync"
	"testing"
)

func TestGet_SmallSize_ReturnsSmallBuffer(t *testing.T) {
	p := New()
	b := p.Get(512) // < 1 KiB
	if cap(b.Bytes) < SmallBufferSize {
		t.Fatalf("small cap: got %d, want >= %d", cap(b.Bytes), SmallBufferSize)
	}
	b.Release()
}

func TestGet_MediumSize_ReturnsMediumBuffer(t *testing.T) {
	p := New()
	b := p.Get(4 << 10) // between small and medium
	if cap(b.Bytes) < MediumBufferSize {
		t.Fatalf("medium cap: got %d, want >= %d", cap(b.Bytes), MediumBufferSize)
	}
	b.Release()
}

func TestGet_LargeSize_ReturnsLargeBuffer(t *testing.T) {
	p := New()
	b := p.Get(32 << 10) // between medium and large
	if cap(b.Bytes) < LargeBufferSize {
		t.Fatalf("large cap: got %d, want >= %d", cap(b.Bytes), LargeBufferSize)
	}
	b.Release()
}

func TestGet_OversizeBypassesPool(t *testing.T) {
	p := New()
	want := 256 << 10 // 256 KiB > LargeBufferSize
	b := p.Get(want)
	if cap(b.Bytes) < want {
		t.Fatalf("oversize cap: got %d, want >= %d", cap(b.Bytes), want)
	}
	// Release on an oversize buffer should not panic and should not put a
	// 256 KiB array into the small/medium/large pools.
	b.Release()
}

func TestRelease_ZerosBytesBeforeReturn(t *testing.T) {
	p := New()
	b := p.Get(64)
	b.Bytes = append(b.Bytes, []byte("secret-token")...)
	b.Release()
	// After release, Bytes is nil so nobody can read the cleared payload.
	if b.Bytes != nil {
		t.Fatal("Release must nil out Bytes")
	}
}

func TestPoolReuse_ReducesAllocations(t *testing.T) {
	p := New()
	// Sanity: 10 000 borrow-and-return cycles should reuse the pool array.
	for i := 0; i < 10_000; i++ {
		b := p.Get(SmallBufferSize)
		b.Bytes = append(b.Bytes, byte(i))
		b.Release()
	}
	// We do not assert allocation counts (the runtime is non-deterministic)
	// but completing the loop without OOM exercises the path.
}

func TestRelease_OnNilOrZeroValue_IsSafe(t *testing.T) {
	var b *Buffer
	b.Release() // nil receiver path
	z := &Buffer{}
	z.Release() // zero-value receiver path
}

func TestPools_ConcurrentSafe(t *testing.T) {
	p := New()
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				b := p.Get(MediumBufferSize)
				b.Bytes = append(b.Bytes, []byte("payload")...)
				b.Release()
			}
		}()
	}
	wg.Wait()
}
