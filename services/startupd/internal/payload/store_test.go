package payload

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadLatestReturnsLastNonEmptyLine(t *testing.T) {
	path := filepath.Join(t.TempDir(), "payload.jsonl")
	if err := os.WriteFile(path, []byte("\n{\"version\":0}\n{\"version\":1}\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	got, err := LoadLatest(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != "{\"version\":1}" {
		t.Fatalf("LoadLatest() = %s", got)
	}
}

func TestLoadLatestMissingFile(t *testing.T) {
	_, err := LoadLatest(filepath.Join(t.TempDir(), "missing.jsonl"))

	if !errors.Is(err, ErrPayloadMissing) {
		t.Fatalf("LoadLatest() error = %v", err)
	}
}

func TestLoadLatestAllowsLargePayloadLine(t *testing.T) {
	path := filepath.Join(t.TempDir(), "payload.jsonl")
	body := "{\"body\":\"" + strings.Repeat("x", 70*1024) + "\"}\n"
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}

	got, err := LoadLatest(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) < 70*1024 {
		t.Fatalf("large payload was truncated to %d bytes", len(got))
	}
}

func BenchmarkLoadLatest(b *testing.B) {
	path := filepath.Join(b.TempDir(), "payload.jsonl")
	if err := os.WriteFile(path, []byte("{\"version\":1,\"body\":\"ok\"}\n"), 0o600); err != nil {
		b.Fatal(err)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := LoadLatest(path); err != nil {
			b.Fatal(err)
		}
	}
}
