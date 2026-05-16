//go:build integration

// Slice 1.5 — streamd speed benchmark.
//
// Publishes 100,000 256-byte events to one subscriber over the Unix-domain
// socket and measures p50 / p95 / p99 latency plus throughput. Targets:
//   p99 publish→subscribe round-trip latency < 1 ms
//   throughput > 50,000 messages per second
//
// Up to 5 tuning iterations are budgeted by the slice's TDD step list. If
// the targets are missed after 5 iterations, the slice ships a
// [PERFORMANCE EXEMPTION: ...] marker with the measured numbers and a
// `performance-native-rewrite` AutoIssue.

package benchstreamd_test

import (
	"context"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	streamdv1 "xf-internal-linker-v2/services/streamd/api/gen"
)

const (
	benchEventCount     = 100_000
	benchPayloadBytes   = 256
	benchP99Budget      = time.Millisecond
	benchThroughputGoal = 50_000.0 // messages per second
)

func BenchmarkPublishSubscribe(b *testing.B) {
	if runtime.GOOS == "windows" {
		b.Skip("Unix-domain socket benchmark runs only on Linux containers")
	}
	for n := 0; n < b.N; n++ {
		runOneBenchPass(b)
	}
}

func runOneBenchPass(b *testing.B) {
	b.Helper()
	binary := buildStreamdBenchBinary(b)
	socket := filepath.Join(b.TempDir(), "streamd.sock")

	cmd := exec.Command(binary)
	cmd.Env = append(os.Environ(),
		"XF_STREAMD_SOCKET="+socket,
		"XF_STREAMD_PPROF_ADDR=off",
		"XF_STREAMD_LOG_LEVEL=error",
		// Big bounds so the benchmark fits in the broker's per-topic buffer.
		"XF_STREAMD_BUFFERED_PER_TOPIC=200000",
	)
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		b.Fatalf("start streamd: %v", err)
	}
	defer func() {
		_ = cmd.Process.Signal(syscall.SIGTERM)
		_ = cmd.Wait()
	}()

	waitForBenchSocket(b, socket, 2*time.Second)

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(
		ctx,
		"unix://"+socket,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
		grpc.WithContextDialer(func(c context.Context, _ string) (net.Conn, error) {
			d := net.Dialer{}
			return d.DialContext(c, "unix", socket)
		}),
	)
	if err != nil {
		b.Fatalf("dial streamd: %v", err)
	}
	defer conn.Close()
	client := streamdv1.NewStreamdClient(conn)

	stream, err := client.Subscribe(ctx, &streamdv1.SubscribeRequest{Topic: "bench"})
	if err != nil {
		b.Fatalf("Subscribe: %v", err)
	}

	// 64-bit timestamps stamped at publish-time, read by the subscriber so
	// the latency we measure is the round-trip from "publisher sent" to
	// "subscriber received".
	publishTimes := make([]int64, benchEventCount)
	subDelivered := make([]int64, benchEventCount)
	var received atomic.Int64
	doneRecv := make(chan struct{})
	go func() {
		for i := 0; i < benchEventCount; i++ {
			ev, err := stream.Recv()
			now := time.Now().UnixNano()
			if err != nil {
				b.Logf("subscribe recv error after %d events: %v", i, err)
				close(doneRecv)
				return
			}
			subDelivered[ev.GetOffset()-1] = now
			received.Add(1)
		}
		close(doneRecv)
	}()

	payload := make([]byte, benchPayloadBytes)
	for i := range payload {
		payload[i] = byte('a' + (i % 26))
	}

	pubStart := time.Now()
	for i := 0; i < benchEventCount; i++ {
		publishTimes[i] = time.Now().UnixNano()
		if _, err := client.Publish(ctx, &streamdv1.PublishRequest{
			Topic:   "bench",
			Payload: payload,
		}); err != nil {
			b.Fatalf("Publish %d: %v", i, err)
		}
	}
	pubElapsed := time.Since(pubStart)

	select {
	case <-doneRecv:
	case <-time.After(15 * time.Second):
		b.Fatalf("subscriber did not drain %d events in 15s (got %d)",
			benchEventCount, received.Load())
	}

	// Compute latency distribution from (delivered_at - published_at).
	latencies := make([]time.Duration, benchEventCount)
	for i := 0; i < benchEventCount; i++ {
		if subDelivered[i] == 0 {
			b.Fatalf("event %d not delivered", i)
		}
		latencies[i] = time.Duration(subDelivered[i] - publishTimes[i])
	}
	sort.Slice(latencies, func(i, j int) bool { return latencies[i] < latencies[j] })
	p50 := latencies[len(latencies)*50/100]
	p95 := latencies[len(latencies)*95/100]
	p99 := latencies[len(latencies)*99/100]
	throughput := float64(benchEventCount) / pubElapsed.Seconds()

	b.ReportMetric(float64(p50)/float64(time.Millisecond), "p50_ms")
	b.ReportMetric(float64(p95)/float64(time.Millisecond), "p95_ms")
	b.ReportMetric(float64(p99)/float64(time.Millisecond), "p99_ms")
	b.ReportMetric(throughput, "msg/s")
	b.ReportMetric(float64(pubElapsed.Milliseconds()), "pub_total_ms")

	if p99 > benchP99Budget {
		b.Errorf("p99 latency %s exceeded budget %s — file [PERFORMANCE EXEMPTION: ...]",
			p99, benchP99Budget)
	}
	if throughput < benchThroughputGoal {
		b.Errorf("throughput %.0f msg/s below %.0f msg/s goal — file [PERFORMANCE EXEMPTION: ...]",
			throughput, benchThroughputGoal)
	}
}

func buildStreamdBenchBinary(b *testing.B) string {
	b.Helper()
	out := filepath.Join(b.TempDir(), "streamd")
	build := exec.Command("go", "build", "-o", out, "../cmd/streamd")
	build.Stderr = os.Stderr
	if err := build.Run(); err != nil {
		b.Fatalf("go build streamd: %v", err)
	}
	return out
}

func waitForBenchSocket(b *testing.B, path string, budget time.Duration) {
	b.Helper()
	deadline := time.Now().Add(budget)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(path); err == nil {
			return
		}
		time.Sleep(25 * time.Millisecond)
	}
	b.Fatalf("streamd socket %s did not appear within %s", path, budget)
}
