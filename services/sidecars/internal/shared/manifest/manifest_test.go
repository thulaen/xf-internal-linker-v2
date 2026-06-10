package manifest

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const validManifest = `
host:
  total_memory_mb: 512
  total_storage_mb: 1024
  retention_hours: 168
  max_image_size_mb: 35
  socket_path: /var/run/xf/sidecars.sock
  storage_path: /var/lib/xf/sidecars
  metrics_port: 6061
  idle_release_seconds: 30
  pruner_interval_seconds: 60
  memory_pressure_threshold_percent: 80

services:
  - name: snapshotd
    apache: "Parquet + Iceberg manifest"
    owning_module: governance
    memory_share_mb: 64
    storage_share_mb: 256
    priority: high
    implemented: true
    rpcs:
      - {name: CreateSnapshot, in: CreateSnapshotRequest, out: Snapshot, streaming: none}
      - {name: Search, in: SearchRequest, out: Snapshot, streaming: server}
  - name: topicd
    apache: Kafka
    owning_module: platform
    memory_share_mb: 32
    storage_share_mb: 32
    priority: medium
    implemented: false
    rpcs:
      - {name: Publish, in: PublishRequest, out: Ack, streaming: none}
`

func TestParse_ValidManifest_NoErrors(t *testing.T) {
	m, err := Parse([]byte(validManifest))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	if len(m.Services) != 2 {
		t.Fatalf("services: got %d, want 2", len(m.Services))
	}
}

func TestParse_DuplicateNames_Rejected(t *testing.T) {
	src := strings.Replace(validManifest, "name: topicd", "name: snapshotd", 1)
	_, err := Parse([]byte(src))
	if err == nil {
		t.Fatal("duplicate names should error")
	}
	if !strings.Contains(err.Error(), "duplicate") {
		t.Fatalf("error should mention duplicate, got %v", err)
	}
}

func TestParse_InvalidPriority_Rejected(t *testing.T) {
	src := strings.Replace(validManifest, "priority: high", "priority: critical", 1)
	_, err := Parse([]byte(src))
	if err == nil {
		t.Fatal("invalid priority should error")
	}
	if !strings.Contains(err.Error(), "priority") {
		t.Fatalf("error should mention priority, got %v", err)
	}
}

func TestParse_MissingSocketPath_Rejected(t *testing.T) {
	src := strings.Replace(validManifest, "socket_path: /var/run/xf/sidecars.sock", "socket_path: \"\"", 1)
	_, err := Parse([]byte(src))
	if err == nil {
		t.Fatal("missing socket_path should error")
	}
}

func TestParse_EmptyRPCList_Rejected(t *testing.T) {
	src := `
host:
  total_memory_mb: 512
  total_storage_mb: 1024
  retention_hours: 168
  socket_path: /var/run/xf/sidecars.sock
  storage_path: /var/lib/xf/sidecars
services:
  - name: empty
    apache: Test
    owning_module: platform
    priority: high
    rpcs: []
`
	_, err := Parse([]byte(src))
	if err == nil {
		t.Fatal("empty rpc list should error")
	}
}

func TestLoad_ReadsFileFromDisk(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "manifest.yaml")
	if err := os.WriteFile(path, []byte(validManifest), 0o644); err != nil {
		t.Fatalf("seed: %v", err)
	}
	m, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if len(m.Services) != 2 {
		t.Fatalf("services: got %d, want 2", len(m.Services))
	}
}

func TestImplementedSplit(t *testing.T) {
	m, err := Parse([]byte(validManifest))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	impl := m.ImplementedServices()
	skel := m.SkeletonServices()
	if len(impl) != 1 || impl[0].Name != "snapshotd" {
		t.Fatalf("implemented: got %v, want [snapshotd]", impl)
	}
	if len(skel) != 1 || skel[0].Name != "topicd" {
		t.Fatalf("skeleton: got %v, want [topicd]", skel)
	}
}

func TestValidate_MaxServicesEnforced(t *testing.T) {
	// 41 services should fail.
	var sb strings.Builder
	sb.WriteString("host:\n  total_memory_mb: 1\n  total_storage_mb: 1\n  retention_hours: 1\n  socket_path: /s\n  storage_path: /d\nservices:\n")
	for i := 0; i < MaxServices+1; i++ {
		sb.WriteString("  - name: svc")
		sb.WriteString(itoa(i))
		sb.WriteString("\n    apache: x\n    owning_module: platform\n    priority: high\n    rpcs:\n      - {name: Ping, in: Empty, out: Ack, streaming: none}\n")
	}
	_, err := Parse([]byte(sb.String()))
	if err == nil {
		t.Fatal("41 services should exceed MaxServices")
	}
}

func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	digits := ""
	for i > 0 {
		digits = string(rune('0'+i%10)) + digits
		i /= 10
	}
	return digits
}

func TestParse_InvalidStreamingMode_Rejected(t *testing.T) {
	src := strings.Replace(validManifest, "streaming: server", "streaming: weird", 1)
	_, err := Parse([]byte(src))
	if err == nil {
		t.Fatal("invalid streaming mode should error")
	}
}

// TestLoad_LiveManifest verifies the actual services.manifest.yaml file at
// the repo root parses and validates. Catches regressions when somebody
// edits the manifest by hand and breaks a YAML key.
func TestLoad_LiveManifest(t *testing.T) {
	m, err := Load("../../../services.manifest.yaml")
	if err != nil {
		t.Fatalf("live manifest: %v", err)
	}
	if got := len(m.Services); got != 40 {
		t.Fatalf("live manifest service count: got %d, want 40", got)
	}
	impl := m.ImplementedServices()
	wantImpl := map[string]bool{
		"snapshotd": true, "bullboard": true, "attrouted": true,
		"schemard": true, "coordd": true, "errord": true,
	}
	if len(impl) != len(wantImpl) {
		t.Fatalf("implemented count: got %d, want %d", len(impl), len(wantImpl))
	}
	for _, s := range impl {
		if !wantImpl[s.Name] {
			t.Fatalf("unexpected implemented service %q (want only the 6 critical)", s.Name)
		}
	}
}
