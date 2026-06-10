// startupd-healthcheck is a tiny static binary used as the Docker
// healthcheck probe. It makes one GET /health request to startupd
// and exits 0 on HTTP 200, 1 on any other outcome.
//
// Because the runtime image is FROM scratch, all probes must be
// self-contained static binaries — no sh, curl, or wget available.
package main

import (
	"net"
	"net/http"
	"net/url"
	"os"
	"time"
)

const (
	defaultHealthAddr = "localhost:8765"
	healthTimeout     = 2 * time.Second
)

func main() {
	target, ok := healthURLFromAddr(os.Getenv("XF_STARTUPD_ADDR"))
	if !ok {
		os.Exit(1)
	}
	client := http.Client{Timeout: healthTimeout}
	// #nosec G704 -- healthURLFromAddr only permits localhost or loopback hosts.
	resp, err := client.Get(target)
	if err != nil {
		os.Exit(1)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusOK {
		os.Exit(1)
	}
}

func healthURLFromAddr(raw string) (string, bool) {
	addr := raw
	if addr == "" || addr == ":8765" {
		addr = defaultHealthAddr
	}
	host, port, err := net.SplitHostPort(addr)
	if err != nil || port == "" {
		return "", false
	}
	if host == "" {
		host = "localhost"
	}
	if !isLoopbackHost(host) {
		return "", false
	}
	return (&url.URL{
		Scheme: "http",
		Host:   net.JoinHostPort(host, port),
		Path:   "/health",
	}).String(), true
}

func isLoopbackHost(host string) bool {
	if host == "localhost" {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}
