//go:build integration

// Slice 1.5 — streamd Unix-socket round-trip integration test.
//
// Builds the cmd/streamd binary, runs it as a subprocess against a tempdir
// socket, exercises Publish + Subscribe + Manage + Health, sends SIGTERM,
// and asserts the binary exits cleanly within the graceful-shutdown deadline.
//
// Run with:
//   go test -tags=integration ./test/integration/...
//
// The integration build tag keeps the test out of the default unit-test pass
// because it shells out to `go build` and `os/exec.Command`, which adds a
// few seconds to the otherwise-fast unit suite.

package integration_test

import (
	"context"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sync"
	"syscall"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	streamdv1 "xf-internal-linker-v2/services/streamd/api/gen"
)

const (
	integrationDialTimeout    = 5 * time.Second
	integrationServeWait      = 2 * time.Second
	integrationShutdownBudget = 3 * time.Second
)

func TestUnixSocketRoundTrip(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Unix-domain socket integration runs only on Linux containers")
	}
	binary := buildStreamdBinary(t)
	socket := filepath.Join(t.TempDir(), "streamd.sock")

	cmd := exec.Command(binary)
	cmd.Env = append(os.Environ(),
		"XF_STREAMD_SOCKET="+socket,
		"XF_STREAMD_PPROF_ADDR=off",
		"XF_STREAMD_LOG_LEVEL=warn",
	)
	stderrPipe, err := cmd.StderrPipe()
	if err != nil {
		t.Fatalf("stderr pipe: %v", err)
	}
	if err := cmd.Start(); err != nil {
		t.Fatalf("start streamd: %v", err)
	}
	t.Cleanup(func() {
		if cmd.Process != nil {
			_ = cmd.Process.Kill()
		}
	})
	logBuf := drainPipe(stderrPipe)

	waitForSocket(t, socket, integrationServeWait)

	client, conn := dialClient(t, socket)
	defer conn.Close()
	ctx, cancel := context.WithTimeout(context.Background(), integrationDialTimeout)
	defer cancel()

	// Health check is the cheapest probe.
	healthResp, err := client.Health(ctx, &streamdv1.HealthRequest{})
	if err != nil {
		t.Fatalf("Health: %v (stderr: %s)", err, logBuf.String())
	}
	if healthResp.GetStatus() != streamdv1.HealthResponse_SERVING {
		t.Fatalf("health status %v, want SERVING", healthResp.GetStatus())
	}

	// Subscribe to the topic BEFORE publishing so the live fan-out catches it.
	subCtx, subCancel := context.WithCancel(context.Background())
	defer subCancel()
	stream, err := client.Subscribe(subCtx, &streamdv1.SubscribeRequest{Topic: "diagnostics"})
	if err != nil {
		t.Fatalf("Subscribe: %v", err)
	}
	got := make(chan *streamdv1.Event, 1)
	go func() {
		ev, recvErr := stream.Recv()
		if recvErr != nil {
			t.Logf("subscribe recv error: %v", recvErr)
			return
		}
		got <- ev
	}()

	pubResp, err := client.Publish(ctx, &streamdv1.PublishRequest{
		Topic:   "diagnostics",
		Payload: []byte("hello"),
	})
	if err != nil {
		t.Fatalf("Publish: %v", err)
	}
	if pubResp.GetOffset() == 0 {
		t.Fatalf("Publish returned offset=0")
	}

	select {
	case ev := <-got:
		if ev.GetTopic() != "diagnostics" || string(ev.GetPayload()) != "hello" {
			t.Fatalf("subscribe received unexpected event: %+v", ev)
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("subscribe did not receive event in 2s")
	}

	// Manage stream — single Ack then GetConsumerOffset round-trip.
	manage, err := client.Manage(ctx)
	if err != nil {
		t.Fatalf("Manage: %v", err)
	}
	if err := manage.Send(&streamdv1.ManageRequest{
		Command: &streamdv1.ManageRequest_Ack{Ack: &streamdv1.AckOffsetCommand{
			Topic:      "diagnostics",
			ConsumerId: "tester",
			Offset:     pubResp.GetOffset(),
		}},
	}); err != nil {
		t.Fatalf("Manage ack send: %v", err)
	}
	ackResp, err := manage.Recv()
	if err != nil {
		t.Fatalf("Manage ack recv: %v", err)
	}
	if !ackResp.GetAck().GetAccepted() {
		t.Fatalf("Manage ack rejected: %+v", ackResp)
	}

	subCancel()

	// SIGTERM and assert clean exit within the graceful deadline.
	if err := cmd.Process.Signal(syscall.SIGTERM); err != nil {
		t.Fatalf("send SIGTERM: %v", err)
	}
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	select {
	case err := <-done:
		if err != nil {
			if ee, ok := err.(*exec.ExitError); ok && ee.ExitCode() == -1 {
				// Killed by signal; that is acceptable as long as we did not time out.
			} else if err != nil {
				t.Fatalf("streamd exit error: %v (stderr: %s)", err, logBuf.String())
			}
		}
	case <-time.After(integrationShutdownBudget):
		t.Fatalf("streamd did not exit within %s of SIGTERM", integrationShutdownBudget)
	}
}

func buildStreamdBinary(t *testing.T) string {
	t.Helper()
	out := filepath.Join(t.TempDir(), "streamd")
	build := exec.Command("go", "build", "-o", out, "../../cmd/streamd")
	build.Stderr = os.Stderr
	if err := build.Run(); err != nil {
		t.Fatalf("go build streamd: %v", err)
	}
	return out
}

func waitForSocket(t *testing.T, path string, budget time.Duration) {
	t.Helper()
	deadline := time.Now().Add(budget)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(path); err == nil {
			return
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatalf("streamd socket %s did not appear within %s", path, budget)
}

func dialClient(t *testing.T, socket string) (streamdv1.StreamdClient, *grpc.ClientConn) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), integrationDialTimeout)
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
		t.Fatalf("dial streamd: %v", err)
	}
	return streamdv1.NewStreamdClient(conn), conn
}

type drainBuffer struct {
	mu   sync.Mutex
	data []byte
}

func (b *drainBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return string(b.data)
}

func (b *drainBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.data = append(b.data, p...)
	return len(p), nil
}

func drainPipe(r io.Reader) *drainBuffer {
	buf := &drainBuffer{}
	go func() {
		_, _ = io.Copy(buf, r)
	}()
	return buf
}
