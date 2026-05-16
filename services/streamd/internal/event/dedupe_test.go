package event

import (
	"encoding/json"
	"errors"
	"os/exec"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestDedupeKeyIsStableForEquivalentJSON(t *testing.T) {
	first := map[string]any{"post_id": 42, "event": "post_updated", "tags": []any{"a", "b"}}
	second := map[string]any{"tags": []any{"a", "b"}, "event": "post_updated", "post_id": 42}

	firstKey, err := DedupeKey("wp", "post_updated", first)
	if err != nil {
		t.Fatalf("first key failed: %v", err)
	}
	secondKey, err := DedupeKey("wp", "post_updated", second)
	if err != nil {
		t.Fatalf("second key failed: %v", err)
	}

	if firstKey != secondKey {
		t.Fatalf("expected stable key, got %q and %q", firstKey, secondKey)
	}
}

func TestVerifySharedSecretFailsClosed(t *testing.T) {
	if VerifySharedSecret("", "secret") {
		t.Fatal("empty configured secret must fail closed")
	}
	if VerifySharedSecret("secret", "") {
		t.Fatal("empty supplied secret must fail closed")
	}
	if VerifySharedSecret("secret", "wrong") {
		t.Fatal("wrong supplied secret must fail")
	}
	if !VerifySharedSecret("secret", "secret") {
		t.Fatal("matching secret must pass")
	}
}

func TestDedupeKeyValidationAndTrim(t *testing.T) {
	payload := map[string]any{"event": "post_updated"}
	if _, err := DedupeKey("", "post_updated", payload); err == nil {
		t.Fatal("empty source must fail")
	}
	if _, err := DedupeKey("wp", "", payload); err == nil {
		t.Fatal("empty event type must fail")
	}
	key, err := DedupeKey(" wp ", " post_updated ", payload)
	if err != nil {
		t.Fatalf("trimmed key failed: %v", err)
	}
	if !strings.HasPrefix(key, "wp:post_updated:") {
		t.Fatalf("expected trimmed key prefix, got %q", key)
	}
}

func TestDedupeKeyRejectsUnsupportedPayload(t *testing.T) {
	if _, err := DedupeKey("wp", "post_updated", make(chan int)); err == nil {
		t.Fatal("unsupported payload must fail")
	}
}

func TestCanonicalJSONCoversPrimitiveAndEscapedValues(t *testing.T) {
	payload := map[string]any{
		"bool":    true,
		"float":   1.25,
		"int64":   int64(99),
		"nil":     nil,
		"escaped": "quote \" slash \\",
	}
	canonical, err := canonicalJSON(payload)
	if err != nil {
		t.Fatalf("canonical json: %v", err)
	}
	want := `{"bool":true,"escaped":"quote \" slash \\","float":1.25,"int64":99,"nil":null}`
	if string(canonical) != want {
		t.Fatalf("expected %s, got %s", want, canonical)
	}
}

func TestCanonicalJSONHandlesLargeObjectsAndTextValues(t *testing.T) {
	payload := map[string]any{}
	for index := range 17 {
		payload[strconv.Itoa(index)] = textValue("value")
	}
	canonical, err := canonicalJSON(payload)
	if err != nil {
		t.Fatalf("canonical json: %v", err)
	}
	if !strings.Contains(string(canonical), `"16":"value"`) {
		t.Fatalf("large object missed text value: %s", canonical)
	}
}

func TestCanonicalJSONReturnsTextMarshalErrors(t *testing.T) {
	_, err := canonicalJSON(textValueWithError{})
	if !errors.Is(err, errTextValue) {
		t.Fatalf("expected text marshal error, got %v", err)
	}
}

func TestGoDedupeKeyIsAtLeastFiveTimesFasterThanPythonBaseline(t *testing.T) {
	if raceEnabled || testing.CoverMode() != "" {
		t.Skip("speed comparison is checked without race or coverage instrumentation")
	}
	const iterations = 25000
	payload := map[string]any{
		"event":   "post_updated",
		"post_id": 42,
		"title":   "Example title",
		"tags":    []any{"alpha", "beta", "gamma"},
	}

	start := time.Now()
	for range iterations {
		if _, err := DedupeKey("wp", "post_updated", payload); err != nil {
			t.Fatalf("go dedupe failed: %v", err)
		}
	}
	goNsPerOp := float64(time.Since(start).Nanoseconds()) / float64(iterations)
	pythonNsPerOp := runPythonDedupeBaseline(t, iterations, payload)
	speedup := pythonNsPerOp / goNsPerOp
	t.Logf("Go dedupe speedup %.2fx; go %.0f ns/op, python %.0f ns/op",
		speedup, goNsPerOp, pythonNsPerOp)
	if speedup < 5.0 {
		t.Fatalf("Go dedupe speedup %.2fx is below 5.00x; go %.0f ns/op, python %.0f ns/op", speedup, goNsPerOp, pythonNsPerOp)
	}
}

func runPythonDedupeBaseline(t *testing.T, iterations int, payload map[string]any) float64 {
	t.Helper()
	rawPayload, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	cmd := exec.Command("python", "testdata/python_dedupe_baseline.py", strconv.Itoa(iterations), string(rawPayload))
	out, err := cmd.Output()
	if err != nil {
		t.Fatalf("python baseline failed: %v", err)
	}
	value, err := strconv.ParseFloat(strings.TrimSpace(string(out)), 64)
	if err != nil {
		t.Fatalf("python baseline output %q is not a number: %v", out, err)
	}
	return value
}

type textValue string

func (value textValue) MarshalText() ([]byte, error) {
	return []byte(value), nil
}

var errTextValue = errors.New("text value failed")

type textValueWithError struct{}

func (textValueWithError) MarshalText() ([]byte, error) {
	return nil, errTextValue
}
