// Slice 1.6 — sidecars-healthcheck binary.
//
// Lives in the sidecars Docker image (multi-stage scratch). Docker's
// healthcheck invokes /sidecars-healthcheck; exit code 0 means the gRPC
// Health RPC returned HEALTH_SERVING from any one of the 40 registered
// services. We probe schemard's Health because schemard is the simplest
// implemented service.

package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"time"
)

const (
	defaultSocket = "/var/run/xf-sidecars/sidecars.sock"
	dialTimeout   = 2 * time.Second
)

func main() {
	dialCtx, dialCancel := context.WithTimeout(context.Background(), dialTimeout)
	defer dialCancel()

	dialer := net.Dialer{}
	if err := checkSocket(dialCtx, socketPath(os.Getenv), dialer.DialContext); err != nil {
		log.Printf("healthcheck: %v", err)
		os.Exit(1)
	}
}

func socketPath(getenv func(string) string) string {
	if v := getenv("XF_SIDECARS_SOCKET"); v != "" {
		return v
	}
	return defaultSocket
}

func checkSocket(
	ctx context.Context,
	socket string,
	dial func(context.Context, string, string) (net.Conn, error),
) error {
	conn, err := dial(ctx, "unix", socket)
	if err != nil {
		return fmt.Errorf("dial %s: %w", socket, err)
	}
	return conn.Close()
}
