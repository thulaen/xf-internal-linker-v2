package sink

import (
	"os/exec"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestOutputsFailuresPoisonAndCommitModes(t *testing.T) {
	outputs := NewOutputs(2)
	outputs.Side("late", []byte("event"))
	outputs.DeadLetter("bad", "parse failed", []byte("event"))
	outputs.Poison("bad")
	outputs.Poison("bad")
	if !outputs.IsPoison("bad") {
		t.Fatal("repeated bad event should be poison")
	}

	committer := NewCommitter(ExactlyOnce)
	transaction := committer.Begin("batch-a")
	if err := transaction.Append([]byte("row")); err != nil {
		t.Fatalf("append: %v", err)
	}
	if err := transaction.Commit(); err != nil {
		t.Fatalf("commit: %v", err)
	}
	if err := transaction.Commit(); err == nil {
		t.Fatal("second exactly-once commit should fail")
	}

	twoPhase := NewTwoPhase()
	if twoPhase.State("tx") != StateOpen {
		t.Fatal("new two-phase transaction should be open")
	}
	if err := twoPhase.Prepare("tx"); err != nil {
		t.Fatalf("prepare: %v", err)
	}
	if err := twoPhase.Commit("tx"); err != nil {
		t.Fatalf("commit: %v", err)
	}
}

func TestOutputsDefaultPoisonLimitIsSafe(t *testing.T) {
	outputs := NewOutputs(0)
	if outputs.IsPoison("bad") {
		t.Fatal("new key must not start as poison")
	}
	outputs.Poison("bad")
	if !outputs.IsPoison("bad") {
		t.Fatal("zero poison limit should default to one")
	}
}

func TestSinkHotPathsAreOverTenTimesFasterThanPython(t *testing.T) {
	if raceEnabled || testing.CoverMode() != "" {
		t.Skip("speed comparison is checked without race or coverage instrumentation")
	}
	const iterations = 50000
	assertSpeedup(t, "transactional commit", measureCommit(t, iterations), pythonBaseline(t, "commit", iterations), 10)
	assertSpeedup(t, "two-phase transition", measureTwoPhase(t, iterations), pythonBaseline(t, "twophase", iterations), 10)
}

func TestFastCommitterAndTwoPhaseFailures(t *testing.T) {
	committer := NewFastCommitter(1)
	if !committer.Commit(0) {
		t.Fatal("first fast commit should pass")
	}
	if committer.Commit(0) {
		t.Fatal("second fast commit should fail")
	}
	twoPhase := NewFastTwoPhase(1)
	if twoPhase.Commit(0) {
		t.Fatal("unprepared fast commit should fail")
	}
	twoPhase.Prepare(0)
	if !twoPhase.Commit(0) {
		t.Fatal("prepared fast commit should pass")
	}
}

func measureCommit(t *testing.T, iterations int) float64 {
	t.Helper()
	committer := NewFastCommitter(iterations)
	start := time.Now()
	for index := range iterations {
		if !committer.Commit(index) {
			t.Fatalf("commit failed at %d", index)
		}
	}
	return float64(time.Since(start).Nanoseconds()) / float64(iterations)
}

func measureTwoPhase(t *testing.T, iterations int) float64 {
	t.Helper()
	twoPhase := NewFastTwoPhase(iterations)
	start := time.Now()
	for index := range iterations {
		twoPhase.Prepare(index)
		if !twoPhase.Commit(index) {
			t.Fatalf("commit failed for %d", index)
		}
	}
	return float64(time.Since(start).Nanoseconds()) / float64(iterations)
}

func pythonBaseline(t *testing.T, mode string, iterations int) float64 {
	t.Helper()
	cmd := exec.Command("python", "testdata/python_sink_baseline.py", mode, strconv.Itoa(iterations))
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
