package timeflow

import (
	"os/exec"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestTimersWatermarksWindowsAndTriggers(t *testing.T) {
	timers := NewTimerWheel()
	timers.Schedule("site-a", time.Unix(20, 0), []byte("refresh"))
	due := timers.PopDue(time.Unix(21, 0))
	if len(due) != 1 || string(due[0].Payload) != "refresh" {
		t.Fatalf("expected delayed timer, got %#v", due)
	}

	watermarks := NewWatermarks(2 * time.Second)
	if mark := watermarks.Observe("site-a", time.Unix(100, 0)); !mark.Equal(time.Unix(98, 0)) {
		t.Fatalf("unexpected watermark %s", mark)
	}
	if !watermarks.IsLate("site-a", time.Unix(97, 0)) {
		t.Fatal("event before watermark must be late")
	}

	if got := TumblingWindow(65*time.Second, time.Minute); got.Start != time.Minute || got.End != 2*time.Minute {
		t.Fatalf("unexpected tumbling window %#v", got)
	}
	if got := SlidingWindows(70*time.Second, time.Minute, 30*time.Second); len(got) != 2 {
		t.Fatalf("expected 2 sliding windows, got %d", len(got))
	}
	session := NewSessionWindow(30 * time.Second)
	session.Observe("site-a", time.Second)
	session.Observe("site-a", 20*time.Second)
	if closed := session.Observe("site-a", time.Minute); len(closed) != 1 {
		t.Fatalf("expected one closed session, got %d", len(closed))
	}

	countTrigger := NewCountTrigger(3)
	if countTrigger.Observe("site-a") {
		t.Fatal("count trigger fired too early")
	}
	if countTrigger.Observe("site-a") {
		t.Fatal("count trigger fired too early")
	}
	if !countTrigger.Observe("site-a") {
		t.Fatal("count trigger should fire on third event")
	}
	if !TimeTrigger(time.Unix(10, 0), time.Unix(11, 0)) {
		t.Fatal("time trigger should fire after deadline")
	}
}

func TestTimerWheelKeepsFutureTimersAndPopsDueInStages(t *testing.T) {
	timers := NewTimerWheel()
	timers.Schedule("site-a", time.Unix(20, 0), []byte("future"))
	timers.Schedule("site-a", time.Unix(10, 0), []byte("due"))

	first := timers.PopDue(time.Unix(15, 0))
	if len(first) != 1 || string(first[0].Payload) != "due" {
		t.Fatalf("expected only the due timer, got %#v", first)
	}
	second := timers.PopDue(time.Unix(25, 0))
	if len(second) != 1 || string(second[0].Payload) != "future" {
		t.Fatalf("expected the kept future timer, got %#v", second)
	}
	if leftover := timers.PopDue(time.Unix(30, 0)); len(leftover) != 0 {
		t.Fatalf("expected no timers left, got %#v", leftover)
	}
}

func TestWindowHelpersRejectUnsafeSettings(t *testing.T) {
	if got := TumblingWindow(time.Second, 0); got != (Window{}) {
		t.Fatalf("zero tumbling size should return empty window, got %#v", got)
	}
	if got := SlidingWindows(time.Second, time.Minute, 0); got != nil {
		t.Fatalf("zero slide should return nil, got %#v", got)
	}
	if got := SlidingWindows(time.Second, time.Nanosecond, 2*time.Nanosecond); got != nil {
		t.Fatalf("size smaller than slide should return nil, got %#v", got)
	}
	session := NewSessionWindow(0)
	if closed := session.Observe("site-a", time.Second); closed != nil {
		t.Fatalf("first session event should not close windows, got %#v", closed)
	}
	if closed := session.Observe("site-a", time.Second+time.Nanosecond); len(closed) != 0 {
		t.Fatalf("zero session gap should default to one nanosecond, got %#v", closed)
	}
	trigger := NewCountTrigger(0)
	if !trigger.Observe("site-a") {
		t.Fatal("zero count trigger should default to firing on first event")
	}
}

func TestWindowHelpersPinBoundaryBehavior(t *testing.T) {
	if got := TumblingWindow(2*time.Nanosecond, time.Nanosecond); got.Start != 2*time.Nanosecond ||
		got.End != 3*time.Nanosecond {
		t.Fatalf("one-nanosecond tumbling window should be valid, got %#v", got)
	}
	windows := SlidingWindows(30*time.Second, time.Minute, 30*time.Second)
	assertWindow(t, windows, 0, 30*time.Second, 90*time.Second)
	assertWindow(t, windows, 1, 0, time.Minute)

	boundary := SlidingWindows(time.Minute, time.Minute, 30*time.Second)
	assertWindow(t, boundary, 0, time.Minute, 2*time.Minute)
	assertWindow(t, boundary, 1, 30*time.Second, 90*time.Second)
	negative := SlidingWindows(-31*time.Second, time.Minute, 30*time.Second)
	assertWindow(t, negative, 0, -60*time.Second, 0)
	if len(negative) != 1 {
		t.Fatalf("expected one negative-time sliding window, got %d", len(negative))
	}
	nanoWindows := SlidingWindows(2*time.Nanosecond, time.Nanosecond, time.Nanosecond)
	assertWindow(t, nanoWindows, 0, 2*time.Nanosecond, 3*time.Nanosecond)
	if len(nanoWindows) != 1 {
		t.Fatalf("expected one nanosecond sliding window, got %d", len(nanoWindows))
	}
}

func TestSessionWindowIncludesBoundaryAndExtendsEnd(t *testing.T) {
	session := NewSessionWindow(10 * time.Second)
	if closed := session.Observe("site-a", 0); len(closed) != 0 {
		t.Fatalf("first event should not close a session, got %#v", closed)
	}
	if closed := session.Observe("site-a", 10*time.Second); len(closed) != 0 {
		t.Fatalf("gap boundary should stay in the same session, got %#v", closed)
	}
	closed := session.Observe("site-a", 21*time.Second)
	if len(closed) != 1 {
		t.Fatalf("expected one closed session, got %#v", closed)
	}
	if closed[0].Start != 0 || closed[0].End != 20*time.Second {
		t.Fatalf("expected closed session [0s,20s), got %#v", closed[0])
	}
}

func TestCountTriggerResetsAfterFire(t *testing.T) {
	trigger := NewCountTrigger(2)
	if trigger.Observe("site-a") {
		t.Fatal("first event should not fire")
	}
	if !trigger.Observe("site-a") {
		t.Fatal("second event should fire")
	}
	if trigger.Observe("site-a") {
		t.Fatal("third event should start the next count")
	}
	if !trigger.Observe("site-a") {
		t.Fatal("fourth event should fire again")
	}
}

func TestTimeflowHotPathsAreOverTenTimesFasterThanPython(t *testing.T) {
	if raceEnabled || testing.CoverMode() != "" {
		t.Skip("speed comparison is checked without race or coverage instrumentation")
	}
	const iterations = 40000
	assertSpeedup(t, "timer scheduling", measureTimerSchedule(t, iterations), pythonBaseline(t, "timer", iterations), 10)
	assertSpeedup(t, "window assignment", measureWindowAssign(iterations), pythonBaseline(t, "window", iterations), 10)
	assertSpeedup(t, "watermark update", measureWatermarkUpdate(iterations), pythonBaseline(t, "watermark", iterations), 10)
}

func TestFastTimerAndWatermarkPaths(t *testing.T) {
	timer := NewFastTimerWheel(2)
	timer.ScheduleAt(10)
	timer.ScheduleAt(11)
	if len(timer.timers) != 2 {
		t.Fatalf("expected 2 fast timers, got %d", len(timer.timers))
	}
	watermarks := NewFastWatermarksByID(2, 1)
	if got := watermarks.ObserveID(0, 10); got != 8 {
		t.Fatalf("expected watermark 8, got %d", got)
	}
	if got := watermarks.ObserveID(0, 9); got != 8 {
		t.Fatalf("watermark should not move backward, got %d", got)
	}
}

func measureTimerSchedule(t *testing.T, iterations int) float64 {
	t.Helper()
	timers := NewFastTimerWheel(iterations)
	start := time.Now()
	for index := range iterations {
		timers.ScheduleAt(int64(index))
	}
	return float64(time.Since(start).Nanoseconds()) / float64(iterations)
}

func measureWindowAssign(iterations int) float64 {
	start := time.Now()
	for index := range iterations {
		_ = TumblingWindow(time.Duration(index)*time.Second, time.Minute)
	}
	return float64(time.Since(start).Nanoseconds()) / float64(iterations)
}

func measureWatermarkUpdate(iterations int) float64 {
	watermarks := NewFastWatermarksByID(1, 1)
	start := time.Now()
	for index := range iterations {
		watermarks.ObserveID(0, int64(index))
	}
	return float64(time.Since(start).Nanoseconds()) / float64(iterations)
}

func pythonBaseline(t *testing.T, mode string, iterations int) float64 {
	t.Helper()
	cmd := exec.Command("python", "testdata/python_timeflow_baseline.py", mode, strconv.Itoa(iterations))
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

func assertWindow(t *testing.T, windows []Window, index int, start time.Duration, end time.Duration) {
	t.Helper()
	if len(windows) <= index {
		t.Fatalf("expected window %d in %#v", index, windows)
	}
	if windows[index].Start != start || windows[index].End != end {
		t.Fatalf("window %d: expected [%s,%s), got %#v", index, start, end, windows[index])
	}
}
