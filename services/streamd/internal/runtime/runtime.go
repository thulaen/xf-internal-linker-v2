package runtime

import (
	"sync"
	"time"
)

type Mode string

const ModeShadow Mode = "shadow"

type Runtime struct {
	mu        sync.RWMutex
	mode      Mode
	paused    bool
	operators map[string]OperatorMetric
	checks    []ShadowResult
}

type OperatorMetric struct {
	Count   uint64
	Errors  uint64
	Latency time.Duration
}

type AdminReport struct {
	Mode      Mode
	Paused    bool
	Operators map[string]OperatorMetric
	Checks    []ShadowResult
}

type ShadowResult struct {
	Name      string
	ParityOK  bool
	Speedup   float64
	LiveReady bool
}

func New() *Runtime {
	return &Runtime{mode: ModeShadow, operators: make(map[string]OperatorMetric)}
}

func (r *Runtime) Mode() Mode {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.mode
}

func (r *Runtime) Record(operator string, latency time.Duration, err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	metric := r.operators[operator]
	metric.Count++
	metric.Latency += latency
	if err != nil {
		metric.Errors++
	}
	r.operators[operator] = metric
}

func (r *Runtime) Pause() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.paused = true
}

func (r *Runtime) Resume() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.paused = false
}

func (r *Runtime) Paused() bool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.paused
}

func (r *Runtime) ShadowCheck(name string, goResult string, pythonResult string, speedup float64) ShadowResult {
	result := ShadowResult{
		Name:      name,
		ParityOK:  goResult == pythonResult,
		Speedup:   speedup,
		LiveReady: goResult == pythonResult && speedup > 10,
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.checks = append(r.checks, result)
	return result
}

func (r *Runtime) AdminReport() AdminReport {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return AdminReport{
		Mode:      r.mode,
		Paused:    r.paused,
		Operators: copyMetrics(r.operators),
		Checks:    append([]ShadowResult(nil), r.checks...),
	}
}

func copyMetrics(metrics map[string]OperatorMetric) map[string]OperatorMetric {
	copied := make(map[string]OperatorMetric, len(metrics))
	for key, metric := range metrics {
		copied[key] = metric
	}
	return copied
}
