package schema

import (
	"os/exec"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestRegistryChecksSchemaCompatibility(t *testing.T) {
	registry := NewRegistry()
	if err := registry.Register("event", 1, []Field{{Name: "id", Type: "string", Required: true}}); err != nil {
		t.Fatalf("register: %v", err)
	}
	if err := registry.Register("event", 2, []Field{{Name: "id", Type: "string", Required: true}, {Name: "title", Type: "string"}}); err != nil {
		t.Fatalf("compatible register: %v", err)
	}
	if err := registry.Register("event", 3, []Field{{Name: "id", Type: "int", Required: true}}); err == nil {
		t.Fatal("incompatible schema should fail")
	}
	if !registry.Compatible("event", 2, map[string]string{"id": "string", "title": "string"}) {
		t.Fatal("expected event payload to be compatible")
	}
}

func TestSchemaCompatibilityIsOverTenTimesFasterThanPython(t *testing.T) {
	if raceEnabled || testing.CoverMode() != "" {
		t.Skip("speed comparison is checked without race or coverage instrumentation")
	}
	const iterations = 60000
	registry := NewRegistry()
	if err := registry.Register("event", 1, []Field{{Name: "id", Type: "string", Required: true}}); err != nil {
		t.Fatalf("register: %v", err)
	}
	validator := registry.Validator("event", 1)
	payload := map[string]string{"id": "string"}
	start := time.Now()
	for range iterations {
		if !validator.Compatible(payload) {
			t.Fatal("schema should be compatible")
		}
	}
	goNsPerOp := float64(time.Since(start).Nanoseconds()) / float64(iterations)
	assertSpeedup(t, "schema compatibility", goNsPerOp, pythonBaseline(t, iterations), 10)
}

func TestValidatorRejectsMissingRequiredField(t *testing.T) {
	registry := NewRegistry()
	if err := registry.Register("event", 1, []Field{{Name: "id", Type: "string", Required: true}}); err != nil {
		t.Fatalf("register: %v", err)
	}
	validator := registry.Validator("event", 1)
	if validator.Compatible(map[string]string{}) {
		t.Fatal("missing required field should fail")
	}
	if registry.Compatible("missing", 1, map[string]string{}) {
		t.Fatal("missing schema should fail")
	}
}

func pythonBaseline(t *testing.T, iterations int) float64 {
	t.Helper()
	cmd := exec.Command("python", "testdata/python_schema_baseline.py", strconv.Itoa(iterations))
	out, err := cmd.Output()
	if err != nil {
		t.Fatalf("python schema baseline failed: %v", err)
	}
	value, err := strconv.ParseFloat(strings.TrimSpace(string(out)), 64)
	if err != nil {
		t.Fatalf("python schema output %q is not a number: %v", out, err)
	}
	return value
}

func assertSpeedup(t *testing.T, name string, goNsPerOp float64, pyNsPerOp float64, want float64) {
	t.Helper()
	speedup := pyNsPerOp / goNsPerOp
	t.Logf("%s speedup %.2fx; go %.0f ns/op, python %.0f ns/op", name, speedup, goNsPerOp, pyNsPerOp)
	if speedup < want {
		t.Fatalf("%s speedup %.2fx is below %.2fx", name, speedup, want)
	}
}
