package timeflow

import (
	"sync"
	"time"
)

type Timer struct {
	Key     string
	At      time.Time
	Payload []byte
}

type TimerWheel struct {
	mu     sync.Mutex
	timers []Timer
}

func NewTimerWheel() *TimerWheel {
	return &TimerWheel{timers: make([]Timer, 0, 64)}
}

func (w *TimerWheel) Schedule(key string, at time.Time, payload []byte) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.timers = append(w.timers, Timer{Key: key, At: at, Payload: append([]byte(nil), payload...)})
}

func (w *TimerWheel) PopDue(now time.Time) []Timer {
	w.mu.Lock()
	defer w.mu.Unlock()
	due := make([]Timer, 0)
	kept := w.timers[:0]
	for _, timer := range w.timers {
		if timer.At.After(now) {
			kept = append(kept, timer)
			continue
		}
		due = append(due, timer)
	}
	w.timers = kept
	return due
}

type Watermarks struct {
	mu       sync.RWMutex
	lag      time.Duration
	bySource map[string]time.Time
}

func NewWatermarks(lag time.Duration) *Watermarks {
	return &Watermarks{lag: lag, bySource: make(map[string]time.Time)}
}

func (w *Watermarks) Observe(source string, eventTime time.Time) time.Time {
	w.mu.Lock()
	defer w.mu.Unlock()
	next := eventTime.Add(-w.lag)
	if current, ok := w.bySource[source]; !ok || next.After(current) {
		w.bySource[source] = next
		return next
	}
	return w.bySource[source]
}

func (w *Watermarks) IsLate(source string, eventTime time.Time) bool {
	w.mu.RLock()
	defer w.mu.RUnlock()
	mark, ok := w.bySource[source]
	return ok && eventTime.Before(mark)
}

type Window struct {
	Start time.Duration
	End   time.Duration
}

func TumblingWindow(at time.Duration, size time.Duration) Window {
	if size <= 0 {
		return Window{}
	}
	start := (at / size) * size
	return Window{Start: start, End: start + size}
}

func SlidingWindows(at time.Duration, size time.Duration, slide time.Duration) []Window {
	if size <= 0 || slide <= 0 {
		return nil
	}
	count := int(size / slide)
	if count <= 0 {
		return nil
	}
	windows := make([]Window, 0, count)
	base := (at / slide) * slide
	for index := 0; index < count; index++ {
		start := base - time.Duration(index)*slide
		if at >= start && at < start+size {
			windows = append(windows, Window{Start: start, End: start + size})
		}
	}
	return windows
}

type SessionWindow struct {
	gap  time.Duration
	open map[string]Window
}

func NewSessionWindow(gap time.Duration) *SessionWindow {
	if gap <= 0 {
		gap = time.Nanosecond
	}
	return &SessionWindow{gap: gap, open: make(map[string]Window)}
}

func (s *SessionWindow) Observe(key string, at time.Duration) []Window {
	current, ok := s.open[key]
	if !ok {
		s.open[key] = Window{Start: at, End: at + s.gap}
		return nil
	}
	if at <= current.End {
		current.End = at + s.gap
		s.open[key] = current
		return nil
	}
	s.open[key] = Window{Start: at, End: at + s.gap}
	return []Window{current}
}

type CountTrigger struct {
	limit  int
	counts map[string]int
}

func NewCountTrigger(limit int) *CountTrigger {
	if limit <= 0 {
		limit = 1
	}
	return &CountTrigger{limit: limit, counts: make(map[string]int)}
}

func (t *CountTrigger) Observe(key string) bool {
	t.counts[key]++
	if t.counts[key] < t.limit {
		return false
	}
	t.counts[key] = 0
	return true
}

func TimeTrigger(deadline time.Time, now time.Time) bool {
	return !now.Before(deadline)
}

type FastTimerWheel struct {
	timers []int64
}

func NewFastTimerWheel(capacity int) *FastTimerWheel {
	return &FastTimerWheel{timers: make([]int64, 0, capacity)}
}

func (w *FastTimerWheel) ScheduleAt(unixNano int64) {
	w.timers = append(w.timers, unixNano)
}

type FastWatermarks struct {
	lag  int64
	byID []int64
}

func NewFastWatermarksByID(lag int64, sources int) *FastWatermarks {
	return &FastWatermarks{lag: lag, byID: make([]int64, sources)}
}

func (w *FastWatermarks) ObserveID(sourceID int, eventTime int64) int64 {
	next := eventTime - w.lag
	if next > w.byID[sourceID] {
		w.byID[sourceID] = next
	}
	return w.byID[sourceID]
}
