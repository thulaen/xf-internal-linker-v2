// Slice 1.5 — streamd-healthcheck binary.
//
// Lives in the streamd Docker image (multi-stage scratch). Docker's
// healthcheck invokes /streamd-healthcheck; exit code 0 means the gRPC
// Health RPC returned SERVING, exit 1 otherwise.

package main

import (
	"context"
	"log"
	"net"
	"os"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	streamdv1 "xf-internal-linker-v2/services/streamd/api/gen"
)

const (
	defaultSocket = "/var/run/xf/streamd.sock"
	dialTimeout   = 2 * time.Second
	callTimeout   = 1500 * time.Millisecond
)

func main() {
	socket := defaultSocket
	if v := os.Getenv("XF_STREAMD_SOCKET"); v != "" {
		socket = v
	}

	dialCtx, dialCancel := context.WithTimeout(context.Background(), dialTimeout)
	defer dialCancel()

	conn, err := grpc.DialContext(
		dialCtx,
		"unix://"+socket,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
		grpc.WithContextDialer(func(ctx context.Context, addr string) (net.Conn, error) {
			d := net.Dialer{}
			return d.DialContext(ctx, "unix", socket)
		}),
	)
	if err != nil {
		log.Printf("healthcheck: dial %s: %v", socket, err)
		os.Exit(1)
	}
	defer conn.Close()

	callCtx, callCancel := context.WithTimeout(context.Background(), callTimeout)
	defer callCancel()
	resp, err := streamdv1.NewStreamdClient(conn).Health(callCtx, &streamdv1.HealthRequest{})
	if err != nil {
		log.Printf("healthcheck: Health RPC: %v", err)
		os.Exit(1)
	}
	if resp.GetStatus() != streamdv1.HealthResponse_SERVING {
		log.Printf("healthcheck: status %s, expected SERVING", resp.GetStatus())
		os.Exit(1)
	}
}
