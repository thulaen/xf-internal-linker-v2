package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"xf-internal-linker-v2/services/startupd/internal/gate"
)

func TestNewServerSetsTimeouts(t *testing.T) {
	server := newServer("127.0.0.1:0", filepath.Join(t.TempDir(), "payload.jsonl"), gate.Config{HTTPClient: &http.Client{}})
	if server.ReadHeaderTimeout <= 0 {
		t.Fatal("ReadHeaderTimeout must be set")
	}
	if server.ReadTimeout <= 0 {
		t.Fatal("ReadTimeout must be set")
	}
	if server.WriteTimeout <= 0 {
		t.Fatal("WriteTimeout must be set")
	}
	if server.IdleTimeout <= 0 {
		t.Fatal("IdleTimeout must be set")
	}
}

func TestPayloadHandlerServesCachedPayload(t *testing.T) {
	path := filepath.Join(t.TempDir(), "payload.jsonl")
	if err := os.WriteFile(path, []byte("{\"version\":1,\"body\":\"ok\"}\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(newMux(path, gate.Config{HTTPClient: &http.Client{}}))
	defer server.Close()

	resp, err := http.Get(server.URL + "/payload")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d", resp.StatusCode)
	}
}

func TestPayloadHandlerMissingPayload(t *testing.T) {
	server := httptest.NewServer(newMux(filepath.Join(t.TempDir(), "missing.jsonl"), gate.Config{HTTPClient: &http.Client{}}))
	defer server.Close()

	resp, err := http.Get(server.URL + "/payload")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("status = %d", resp.StatusCode)
	}
}

func TestHealthAndPprofRoutes(t *testing.T) {
	server := httptest.NewServer(newMux(filepath.Join(t.TempDir(), "payload.jsonl"), gate.Config{HTTPClient: &http.Client{}}))
	defer server.Close()

	for _, path := range []string{"/health", "/debug/pprof/"} {
		resp, err := http.Get(server.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		if err := resp.Body.Close(); err != nil {
			t.Fatalf("%s response close: %v", path, err)
		}
		if resp.StatusCode != http.StatusOK {
			t.Fatalf("%s status = %d", path, resp.StatusCode)
		}
	}
}
