package main

import (
	"context"
	"net"
	"testing"
	"time"
)

type closeTrackingConn struct {
	net.Conn
	closed bool
}

func (c *closeTrackingConn) Close() error {
	c.closed = true
	return nil
}

func TestSocketPathUsesEnvironmentOverride(t *testing.T) {
	got := socketPath(func(name string) string {
		if name == "XF_SIDECARS_SOCKET" {
			return "/tmp/custom.sock"
		}
		return ""
	})
	if got != "/tmp/custom.sock" {
		t.Fatalf("socketPath() = %q, want /tmp/custom.sock", got)
	}
}

func TestSocketPathDefaultMatchesComposeMount(t *testing.T) {
	got := socketPath(func(string) string { return "" })
	if got != "/var/run/xf-sidecars/sidecars.sock" {
		t.Fatalf("socketPath() = %q, want /var/run/xf-sidecars/sidecars.sock", got)
	}
}

func TestCheckSocketDialsAndClosesUnixSocket(t *testing.T) {
	conn := &closeTrackingConn{}
	var gotNetwork, gotAddress string

	err := checkSocket(
		context.Background(),
		"/tmp/sidecars.sock",
		func(_ context.Context, network string, address string) (net.Conn, error) {
			gotNetwork = network
			gotAddress = address
			return conn, nil
		},
	)
	if err != nil {
		t.Fatalf("checkSocket() error = %v", err)
	}
	if gotNetwork != "unix" || gotAddress != "/tmp/sidecars.sock" {
		t.Fatalf("dialed %s %s, want unix /tmp/sidecars.sock", gotNetwork, gotAddress)
	}
	if !conn.closed {
		t.Fatal("checkSocket() did not close the connection")
	}
}

func TestCheckSocketReportsDialFailure(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()

	err := checkSocket(
		ctx,
		"/tmp/missing.sock",
		func(context.Context, string, string) (net.Conn, error) {
			return nil, net.ErrClosed
		},
	)
	if err == nil {
		t.Fatal("checkSocket() error = nil, want failure")
	}
}
