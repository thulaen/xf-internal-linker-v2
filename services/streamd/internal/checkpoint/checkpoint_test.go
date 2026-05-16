package checkpoint

import (
	"os/exec"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestCheckpointSavepointRestoreAndCatalog(t *testing.T) {
	catalog := NewCatalog()
	checkpoint := catalog.Checkpoint("job-a", map[string]uint64{"source": 10}, 256)
	savepoint := catalog.Savepoint("job-a", map[string]uint64{"source": 11}, 300)
	if checkpoint.Kind != KindCheckpoint || savepoint.Kind != KindSavepoint {
		t.Fatalf("unexpected snapshot kinds: %s %s", checkpoint.Kind, savepoint.Kind)
	}
	if err := catalog.ValidateRestore("job-a", savepoint.ID, []string{"source"}); err != nil {
		t.Fatalf("restore should validate: %v", err)
	}
	if err := catalog.ValidateRestore("job-a", savepoint.ID, []string{"missing"}); err == nil {
		t.Fatal("restore with missing step must fail")
	}
	if len(catalog.List("job-a")) != 2 {
		t.Fatal("snapshot catalog should list both snapshots")
	}
}

func TestCheckpointHotPathsAreOverTenTimesFasterThanPython(t *testing.T) {
	if raceEnabled || testing.CoverMode() != "" {
		t.Skip("speed comparison is checked without race or coverage instrumentation")
	}
	const iterations = 40000
	assertSpeedup(t, "checkpoint metadata write", measureCheckpointWrite(iterations), pythonBaseline(t, "write", iterations), 10)
	assertSpeedup(t, "savepoint restore validation", measureRestoreValidate(t, iterations), pythonBaseline(t, "restore", iterations), 10)
}

func TestFastCatalogRecordAndRestoreCheck(t *testing.T) {
	catalog := NewFastCatalog(2)
	if id := catalog.Record(7, 22, 64); id != 1 {
		t.Fatalf("expected first snapshot id 1, got %d", id)
	}
	if !catalog.CanRestore(7) {
		t.Fatal("recorded step should restore")
	}
	if catalog.CanRestore(8) {
		t.Fatal("unrecorded step should not restore")
	}
}

func measureCheckpointWrite(iterations int) float64 {
	catalog := NewFastCatalog(iterations)
	start := time.Now()
	for index := range iterations {
		catalog.Record(1, uint64(index), 64)
	}
	return float64(time.Since(start).Nanoseconds()) / float64(iterations)
}

func measureRestoreValidate(t *testing.T, iterations int) float64 {
	t.Helper()
	catalog := NewFastCatalog(1)
	catalog.Record(1, 1, 64)
	start := time.Now()
	for range iterations {
		if !catalog.CanRestore(1) {
			t.Fatal("restore validate failed")
		}
	}
	return float64(time.Since(start).Nanoseconds()) / float64(iterations)
}

func pythonBaseline(t *testing.T, mode string, iterations int) float64 {
	t.Helper()
	cmd := exec.Command("python", "testdata/python_checkpoint_baseline.py", mode, strconv.Itoa(iterations))
	out, err := cmd.Output()
	if err != nil {
		t.Fatalf("python baseline %s failed: %v", mode, err)
	}
	value, err := strconv.ParseFloat(strings.TrimSpace(string(out)), 64)
	if err != nil {
		t.Fatalf("python baseline output %q is not a number: %v", out, err)
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
