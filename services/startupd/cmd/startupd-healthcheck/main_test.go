package main

import "testing"

func TestHealthURLFromAddrDefaultsToLocalhost(t *testing.T) {
	got, ok := healthURLFromAddr("")
	if !ok {
		t.Fatal("empty health address should be accepted as the localhost default")
	}
	if got != "http://localhost:8765/health" {
		t.Fatalf("default URL: got %q", got)
	}
}

func TestHealthURLFromAddrAllowsLoopbackOnly(t *testing.T) {
	cases := []string{"127.0.0.1:8765", "[::1]:8765", "localhost:8765"}
	for _, raw := range cases {
		if _, ok := healthURLFromAddr(raw); !ok {
			t.Fatalf("loopback address %q should be accepted", raw)
		}
	}
	if _, ok := healthURLFromAddr("example.com:8765"); ok {
		t.Fatal("external health address should be rejected")
	}
}
